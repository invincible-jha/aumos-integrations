# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
GovernedTool — wraps any LangChain BaseTool with an AumOS governance gate.

Use this when you want per-tool governance configuration rather than a single
callback that applies uniform rules to all tools. Each ``GovernedTool`` instance
carries its own trust level requirement, budget category, and denial handling.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from langchain_core.tools import BaseTool
from pydantic import Field

from .errors import GovernanceDeniedError, ToolSkippedError
from .types import DeniedAction

logger = logging.getLogger(__name__)

_DENIAL_SKIP_MESSAGE = "[governance] tool call skipped — policy denied this request"


class GovernedTool(BaseTool):
    """
    A LangChain ``BaseTool`` wrapper that adds an AumOS governance gate.

    Any tool call is evaluated against the governance engine before the inner
    tool is invoked. If the engine denies the call, the wrapper either raises
    ``GovernanceDeniedError``, returns a denial message, or logs and proceeds —
    depending on ``on_denied``.

    Args:
        tool: The LangChain ``BaseTool`` to wrap.
        engine: An initialized ``aumos-governance`` ``GovernanceEngine`` instance.
        required_trust_level: Minimum trust level the agent must hold to run
            this tool. Passed to the engine as metadata; enforcement is
            performed by the engine, not this wrapper.
        budget_category: Optional budget category label. When provided, the
            engine can apply spending-envelope enforcement for this category.
        on_denied: Denial handling mode. ``'raise'`` | ``'skip'`` | ``'log'``.
            Defaults to ``'raise'``.
        agent_id: Agent identifier used in governance evaluations. Defaults to
            ``'default'``.

    Example::

        from langchain_aumos import GovernedTool

        governed = GovernedTool(
            tool=search_tool,
            engine=engine,
            required_trust_level=2,
            budget_category="web_search",
        )
    """

    # Pydantic v2 fields — BaseTool uses model_fields so we declare extras here.
    # The inner tool, engine, and settings are stored as private attributes to
    # avoid conflicts with BaseTool's own field declarations.
    name: str = Field(default="governed_tool")
    description: str = Field(default="A tool wrapped with AumOS governance.")

    # Private state (not Pydantic fields)
    _inner_tool: BaseTool
    _engine: Any
    _required_trust_level: int
    _budget_category: Optional[str]
    _on_denied: DeniedAction
    _agent_id: str

    def __init__(
        self,
        tool: BaseTool,
        engine: Any,
        required_trust_level: int = 0,
        budget_category: Optional[str] = None,
        on_denied: DeniedAction | str = DeniedAction.RAISE,
        agent_id: str = "default",
    ) -> None:
        super().__init__(
            name=tool.name,
            description=tool.description,
        )
        # Store as private attributes after super().__init__ so Pydantic does not
        # try to validate them as model fields.
        object.__setattr__(self, "_inner_tool", tool)
        object.__setattr__(self, "_engine", engine)
        object.__setattr__(self, "_required_trust_level", required_trust_level)
        object.__setattr__(self, "_budget_category", budget_category)
        object.__setattr__(
            self,
            "_on_denied",
            DeniedAction(on_denied) if isinstance(on_denied, str) else on_denied,
        )
        object.__setattr__(self, "_agent_id", agent_id)

    # ------------------------------------------------------------------
    # Synchronous execution
    # ------------------------------------------------------------------

    def _run(self, *args: Any, **kwargs: Any) -> str:
        """
        Check governance, then delegate to the inner tool's ``_run`` method.

        Returns the inner tool's output string on success, or a denial message
        string when ``on_denied='skip'``.

        Raises:
            GovernanceDeniedError: When governance denies and ``on_denied='raise'``.
        """
        decision = self._evaluate_sync(tool_input=self._serialize_input(args, kwargs))

        if not self._is_allowed(decision):
            reason = self._extract_reason(decision)
            return self._handle_denial_run(reason, decision)

        result = self._inner_tool._run(*args, **kwargs)
        self._audit_success(str(result))
        return str(result)

    # ------------------------------------------------------------------
    # Asynchronous execution
    # ------------------------------------------------------------------

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        """
        Async version of ``_run``. Evaluates governance asynchronously, then
        delegates to the inner tool's ``_arun`` method.

        Raises:
            GovernanceDeniedError: When governance denies and ``on_denied='raise'``.
        """
        decision = await self._evaluate_async(
            tool_input=self._serialize_input(args, kwargs)
        )

        if not self._is_allowed(decision):
            reason = self._extract_reason(decision)
            return self._handle_denial_run(reason, decision)

        result = await self._inner_tool._arun(*args, **kwargs)
        self._audit_success(str(result))
        return str(result)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_eval_kwargs(self, tool_input: str) -> dict[str, Any]:
        """Build the keyword arguments for a governance evaluation call."""
        eval_kwargs: dict[str, Any] = {
            "agent_id": self._agent_id,
            "scope": f"tool:{self._inner_tool.name}",
        }
        if self._budget_category is not None:
            eval_kwargs["budget_category"] = self._budget_category
        if self._required_trust_level > 0:
            eval_kwargs["required_trust_level"] = self._required_trust_level
        # Attempt to extract an amount from JSON input
        amount = self._extract_amount_from_input(tool_input)
        if amount is not None:
            eval_kwargs["amount"] = amount
        return eval_kwargs

    def _evaluate_sync(self, tool_input: str) -> Any:
        """Submit a synchronous governance evaluation."""
        return self._engine.evaluate_sync(**self._build_eval_kwargs(tool_input))

    async def _evaluate_async(self, tool_input: str) -> Any:
        """Submit an asynchronous governance evaluation."""
        if hasattr(self._engine, "evaluate"):
            return await self._engine.evaluate(**self._build_eval_kwargs(tool_input))
        # Fallback for engines that only expose evaluate_sync
        return self._engine.evaluate_sync(**self._build_eval_kwargs(tool_input))

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

    def _handle_denial_run(self, reason: str, decision: Any) -> str:
        """
        Act on a denial in the context of a ``_run`` / ``_arun`` call.

        RAISE: Raise ``GovernanceDeniedError``.
        SKIP: Return the denial message string (agent sees it as tool output).
        LOG: Log and return an empty string, allowing the agent to continue.
        """
        if self._on_denied == DeniedAction.RAISE:
            raise GovernanceDeniedError(
                tool_name=self._inner_tool.name,
                agent_id=self._agent_id,
                reason=reason,
                decision=decision,
            )
        elif self._on_denied == DeniedAction.SKIP:
            logger.info(
                "GovernedTool '%s' skipped for agent '%s': %s",
                self._inner_tool.name,
                self._agent_id,
                reason,
            )
            return _DENIAL_SKIP_MESSAGE
        else:
            # DeniedAction.LOG — record and return empty string
            logger.warning(
                "Governance denied tool '%s' for agent '%s' (logged, execution continues): %s",
                self._inner_tool.name,
                self._agent_id,
                reason,
            )
            return ""

    def _audit_success(self, output: str) -> None:
        """Record a successful tool execution in the audit trail."""
        if hasattr(self._engine, "record_audit_event"):
            self._engine.record_audit_event(
                agent_id=self._agent_id,
                tool_name=self._inner_tool.name,
                succeeded=True,
                output_preview=output[:256],
            )

    def _serialize_input(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
        """Serialize tool input to a string for amount extraction."""
        try:
            if args:
                return json.dumps(args[0]) if not isinstance(args[0], str) else args[0]
            return json.dumps(kwargs) if kwargs else ""
        except (TypeError, ValueError):
            return str(args) if args else str(kwargs)

    def _extract_amount_from_input(self, tool_input: str) -> float | None:
        """
        Attempt to extract a numeric ``amount`` field from a JSON tool input.

        Returns None if the input is not JSON or contains no ``amount`` field.
        This is a best-effort extraction — missing amounts are always valid.
        """
        try:
            parsed = json.loads(tool_input)
            if isinstance(parsed, dict):
                raw = parsed.get("amount")
                if raw is not None:
                    return float(raw)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        return None


def govern(
    tool: BaseTool,
    engine: Any,
    *,
    required_trust_level: int = 0,
    budget_category: Optional[str] = None,
    on_denied: DeniedAction | str = DeniedAction.RAISE,
    agent_id: str = "default",
) -> GovernedTool:
    """
    Convenience function to wrap a tool with governance.

    Equivalent to ``GovernedTool(tool, engine, ...)``.

    Example::

        from langchain_aumos import govern

        tools = [govern(t, engine) for t in raw_tools]
    """
    return GovernedTool(
        tool=tool,
        engine=engine,
        required_trust_level=required_trust_level,
        budget_category=budget_category,
        on_denied=on_denied,
        agent_id=agent_id,
    )
