# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
GovernedCrewTool — wraps a CrewAI tool with an AumOS governance gate.

This module provides the per-tool governance layer for CrewAI integrations.
Each ``GovernedCrewTool`` instance wraps a single CrewAI-compatible tool and
intercepts every call to run a governance checkpoint before delegating to the
underlying tool.

Use ``wrap_tools()`` to govern a list of tools in one call. Use
``GovernedCrewTool`` directly when you need per-tool configuration such as
a specific trust level requirement or budget category.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .config import CrewGovernanceConfig
from .errors import GovernanceDeniedError
from .types import AuditRecord, DeniedAction, ToolCallContext

logger = logging.getLogger(__name__)

_DENIAL_SKIP_MESSAGE = "[governance] tool call skipped — policy denied this request"


class GovernedCrewTool:
    """
    Wraps a CrewAI tool with an AumOS governance gate.

    Uses composition — the original tool object is held as a private attribute.
    All attribute access except ``run`` and ``_run`` is delegated to the inner
    tool so that CrewAI's internal tool registry sees the expected interface.

    Args:
        tool: Any CrewAI-compatible tool object. Must expose a ``name``
            attribute and a callable ``run`` or ``_run`` method.
        engine: An initialized ``aumos-governance`` ``GovernanceEngine`` instance.
        agent_role: The role string of the agent using this tool. Used as the
            agent identifier in governance evaluations.
        config: Optional ``CrewGovernanceConfig`` controlling denial handling,
            scope mapping, and audit behaviour.
        required_trust_level: Minimum trust level the agent must hold to invoke
            this tool. Passed to the engine as metadata; enforcement is performed
            by the engine, not this wrapper. Defaults to ``0`` (no requirement).
        budget_category: Optional budget category label. When provided, the
            engine can apply spending-envelope enforcement for this category.

    Example::

        from crewai_aumos import GovernedCrewTool

        governed = GovernedCrewTool(
            tool=search_tool,
            engine=engine,
            agent_role="researcher",
            required_trust_level=1,
            budget_category="web_search",
        )
    """

    def __init__(
        self,
        tool: Any,
        engine: Any,
        agent_role: str,
        config: CrewGovernanceConfig | None = None,
        required_trust_level: int = 0,
        budget_category: Optional[str] = None,
    ) -> None:
        self._tool = tool
        self._engine = engine
        self._agent_role = agent_role
        self._config: CrewGovernanceConfig = config or CrewGovernanceConfig()
        self._required_trust_level = required_trust_level
        self._budget_category = budget_category

    # ------------------------------------------------------------------
    # Delegate name and description to the inner tool so CrewAI sees
    # the correct metadata regardless of whether it reads the attribute
    # or inspects the object.
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Return the inner tool's name."""
        return str(getattr(self._tool, "name", type(self._tool).__name__))

    @property
    def description(self) -> str:
        """Return the inner tool's description."""
        return str(getattr(self._tool, "description", ""))

    # ------------------------------------------------------------------
    # Governed execution
    # ------------------------------------------------------------------

    def run(self, *args: Any, **kwargs: Any) -> str:
        """
        Check governance before running the underlying tool.

        Evaluates the governance engine synchronously. On permit, delegates to
        the inner tool's ``run`` method (falling back to ``_run`` if ``run`` is
        absent). On denial, acts according to ``config.on_denied``.

        Returns:
            The inner tool's output string on success, or a denial message when
            ``on_denied='skip'``.

        Raises:
            GovernanceDeniedError: When governance denies and ``on_denied='raise'``.
        """
        serialized = self._serialize_input(args, kwargs)
        context = self._build_tool_context(serialized)
        decision = self._evaluate_sync(context)

        if not self._is_allowed(decision):
            reason = self._extract_reason(decision)
            return self._handle_denial(reason, decision)

        result = self._invoke_inner_tool(*args, **kwargs)
        self._audit_success(result)
        return result

    # CrewAI may call ``_run`` directly on some tool types; proxy it here.
    def _run(self, *args: Any, **kwargs: Any) -> str:
        """Proxy to ``run`` so CrewAI can invoke this wrapper via either entry point."""
        return self.run(*args, **kwargs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_tool_context(self, serialized_input: str) -> ToolCallContext:
        """Build a ``ToolCallContext`` for this tool invocation."""
        scope = self._config.scope_for_tool(self.name)
        amount = self._extract_amount(serialized_input)
        return ToolCallContext(
            tool_name=self.name,
            agent_role=self._agent_role,
            scope=scope,
            serialized_input=serialized_input,
            amount=amount,
        )

    def _build_eval_kwargs(self, context: ToolCallContext) -> dict[str, Any]:
        """Build keyword arguments for a governance evaluation call."""
        eval_kwargs: dict[str, Any] = {
            "agent_id": context.agent_role,
            "scope": context.scope,
        }
        if self._budget_category is not None:
            eval_kwargs["budget_category"] = self._budget_category
        if self._required_trust_level > 0:
            eval_kwargs["required_trust_level"] = self._required_trust_level
        if context.amount is not None:
            eval_kwargs["amount"] = context.amount
        return eval_kwargs

    def _evaluate_sync(self, context: ToolCallContext) -> Any:
        """Submit a synchronous governance evaluation."""
        return self._engine.evaluate_sync(**self._build_eval_kwargs(context))

    def _invoke_inner_tool(self, *args: Any, **kwargs: Any) -> str:
        """Call the inner tool's run or _run method."""
        if hasattr(self._tool, "run") and callable(self._tool.run):
            result = self._tool.run(*args, **kwargs)
        elif hasattr(self._tool, "_run") and callable(self._tool._run):
            result = self._tool._run(*args, **kwargs)
        else:
            raise TypeError(
                f"Tool '{self.name}' does not expose a callable 'run' or '_run' method."
            )
        return str(result)

    def _is_allowed(self, decision: Any) -> bool:
        """Return True if the governance decision permits the tool call."""
        if hasattr(decision, "allowed"):
            return bool(decision.allowed)
        return bool(decision)

    def _extract_reason(self, decision: Any) -> str:
        """Return a human-readable denial reason from the governance decision."""
        if hasattr(decision, "reason") and decision.reason:
            return str(decision.reason)
        return "governance policy denied this tool call"

    def _handle_denial(self, reason: str, decision: Any) -> str:
        """
        Act on a denial according to the configured ``on_denied`` mode.

        RAISE: Raise ``GovernanceDeniedError``.
        SKIP: Log and return the denial skip message string.
        LOG: Log at WARNING level and return an empty string.
        """
        if self._config.on_denied == DeniedAction.RAISE:
            raise GovernanceDeniedError(
                subject=self.name,
                agent_role=self._agent_role,
                reason=reason,
                decision=decision,
            )
        elif self._config.on_denied == DeniedAction.SKIP:
            logger.info(
                "GovernedCrewTool '%s' skipped for agent role '%s': %s",
                self.name,
                self._agent_role,
                reason,
            )
            return _DENIAL_SKIP_MESSAGE
        else:
            # DeniedAction.LOG — record and return empty string
            logger.warning(
                "Governance denied tool '%s' for agent role '%s' (logged, execution "
                "continues): %s",
                self.name,
                self._agent_role,
                reason,
            )
            return ""

    def _audit_success(self, output: str) -> None:
        """Record a successful tool execution in the audit trail."""
        if not self._config.audit_all_calls:
            return
        preview_len = self._config.audit_output_preview_length
        preview: str | None = output[:preview_len] if preview_len > 0 else None
        record = AuditRecord(
            tool_name=self.name,
            agent_role=self._agent_role,
            succeeded=True,
            output_preview=preview,
        )
        self._write_audit(record)

    def _write_audit(self, record: AuditRecord) -> None:
        """Write an audit record to the governance engine's audit trail."""
        if hasattr(self._engine, "record_audit_event"):
            self._engine.record_audit_event(
                agent_id=record.agent_role,
                tool_name=record.tool_name,
                succeeded=record.succeeded,
                error_message=record.error_message,
                output_preview=record.output_preview,
            )
        else:
            logger.debug(
                "Audit: tool='%s' agent_role='%s' succeeded=%s",
                record.tool_name,
                record.agent_role,
                record.succeeded,
            )

    def _serialize_input(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
        """Serialize tool arguments to a string for amount extraction and audit."""
        try:
            if args:
                return json.dumps(args[0]) if not isinstance(args[0], str) else args[0]
            return json.dumps(kwargs) if kwargs else ""
        except (TypeError, ValueError):
            return str(args) if args else str(kwargs)

    def _extract_amount(self, serialized_input: str) -> float | None:
        """
        Attempt to extract a numeric amount field from JSON-serialized tool input.

        Returns None if ``config.amount_field`` is not set, the input is not valid
        JSON, or the field is absent. Missing amounts are always valid.
        """
        if self._config.amount_field is None:
            return None
        try:
            parsed = json.loads(serialized_input)
            if isinstance(parsed, dict):
                raw = parsed.get(self._config.amount_field)
                if raw is not None:
                    return float(raw)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        return None

    # ------------------------------------------------------------------
    # Transparent attribute delegation
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attribute access to the inner tool."""
        return getattr(self._tool, name)

    def __repr__(self) -> str:
        return f"GovernedCrewTool(tool={self.name!r}, agent_role={self._agent_role!r})"


def wrap_tools(
    tools: list[Any],
    engine: Any,
    agent_role: str,
    config: CrewGovernanceConfig | None = None,
    required_trust_level: int = 0,
) -> list[GovernedCrewTool]:
    """
    Wrap a list of CrewAI tools with governance gates.

    Convenience function equivalent to calling ``GovernedCrewTool(tool, engine, ...)``
    for every tool in the list. All tools receive the same agent role, config,
    and trust level requirement.

    Args:
        tools: List of CrewAI-compatible tool objects to wrap.
        engine: An initialized ``aumos-governance`` ``GovernanceEngine`` instance.
        agent_role: The role string of the agent that will use these tools.
        config: Optional ``CrewGovernanceConfig``. Shared across all wrapped tools.
        required_trust_level: Minimum trust level applied to all wrapped tools.

    Returns:
        A list of ``GovernedCrewTool`` instances in the same order as ``tools``.

    Example::

        from crewai_aumos import wrap_tools

        governed_tools = wrap_tools(raw_tools, engine, agent_role="analyst")
    """
    return [
        GovernedCrewTool(
            tool=tool,
            engine=engine,
            agent_role=agent_role,
            config=config,
            required_trust_level=required_trust_level,
        )
        for tool in tools
    ]
