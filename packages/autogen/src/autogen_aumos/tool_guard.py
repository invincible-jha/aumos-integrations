# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
ToolGuard — standalone tool execution governance for AutoGen.

``ToolGuard`` evaluates governance at function/tool call boundaries before an
AutoGen agent executes a registered function. It can be used standalone (by
calling ``check_tool`` directly from a function executor or hook) or via
``GovernedConversableAgent``, which installs it as a function pre-execution
interceptor.

The guard is a pure checkpoint adapter: it calls ``engine.evaluate_sync()``
with the agent name, tool name, and scope, then acts on the returned decision.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .config import AutoGenGovernanceConfig
from .errors import GovernanceDeniedError
from .types import AuditRecord, DeniedAction, GuardResult, ToolCallContext

logger = logging.getLogger(__name__)

_BLOCK_RESULT = "[governance] tool call blocked — policy denied this function execution"


class ToolGuard:
    """
    Standalone tool execution governance for AutoGen.

    Evaluates a governance checkpoint before an AutoGen agent executes any
    registered function or tool. The check uses the agent name, function name,
    and a scope derived from the function name (or the configured default).

    Args:
        engine: An initialized ``aumos-governance`` ``GovernanceEngine`` instance.
        config: Optional ``AutoGenGovernanceConfig``. If omitted, defaults are used.

    Example::

        from autogen_aumos import ToolGuard

        guard = ToolGuard(engine=engine)
        result = guard.check_tool(
            agent_name="executor",
            tool_name="run_shell_command",
            args={"command": "ls -la"},
        )
        if not result.permitted:
            return {"error": f"Governance denied: {result.reason}"}
    """

    def __init__(
        self,
        engine: Any,
        config: Optional[AutoGenGovernanceConfig] = None,
    ) -> None:
        self._engine = engine
        self._config: AutoGenGovernanceConfig = config or AutoGenGovernanceConfig()

    def check_tool(
        self,
        agent_name: str,
        tool_name: str,
        args: Optional[dict[str, Any]] = None,
    ) -> GuardResult:
        """
        Evaluate governance before executing a tool or function.

        Calls ``engine.evaluate_sync()`` with the agent name as agent ID and the
        configured scope for the tool. Returns a ``GuardResult`` describing the
        decision.

        When ``on_denied`` is ``'raise'``, this method raises
        ``GovernanceDeniedError`` on denial instead of returning a result with
        ``permitted=False``.

        Args:
            agent_name: Name of the agent attempting to execute the tool.
            tool_name: Name of the function or tool being invoked.
            args: Optional dictionary of arguments passed to the function.
                Used to extract a spend amount when ``config.amount_field`` is set.

        Returns:
            ``GuardResult`` with ``permitted=True`` if governance allows the call,
            or ``permitted=False`` with a denial reason under ``'block'`` or
            ``'log'`` mode.

        Raises:
            GovernanceDeniedError: When governance denies and ``on_denied='raise'``.
        """
        resolved_args = args or {}
        scope = self._config.scope_for_tool(tool_name)
        amount = self._extract_amount(resolved_args)

        context = ToolCallContext(
            agent_name=agent_name,
            tool_name=tool_name,
            scope=scope,
            args=resolved_args,
            amount=amount,
        )
        decision = self._evaluate(context)
        permitted = self._is_allowed(decision)

        if not permitted:
            reason = self._extract_reason(decision)
            self._handle_denial(
                agent_name=agent_name,
                tool_name=tool_name,
                scope=scope,
                reason=reason,
                decision=decision,
            )
            # Only reached under BLOCK or LOG mode
            self._write_audit(
                AuditRecord(
                    subject=tool_name,
                    agent_name=agent_name,
                    succeeded=False,
                    error_message=reason,
                )
            )
            return GuardResult(
                permitted=False,
                reason=reason,
                scope=scope,
                agent_name=agent_name,
            )

        if self._config.audit_all_actions:
            self._write_audit(
                AuditRecord(
                    subject=tool_name,
                    agent_name=agent_name,
                    succeeded=True,
                )
            )
        return GuardResult(
            permitted=True,
            reason="",
            scope=scope,
            agent_name=agent_name,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evaluate(self, context: ToolCallContext) -> Any:
        """Submit a synchronous governance evaluation for the tool context."""
        eval_kwargs: dict[str, Any] = {
            "agent_id": context.agent_name,
            "scope": context.scope,
        }
        if context.amount is not None:
            eval_kwargs["amount"] = context.amount
        return self._engine.evaluate_sync(**eval_kwargs)

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

    def _handle_denial(
        self,
        agent_name: str,
        tool_name: str,
        scope: str,
        reason: str,
        decision: Any,
    ) -> None:
        """
        Act on a denial according to the configured ``on_denied`` mode.

        RAISE: Raise ``GovernanceDeniedError``.
        BLOCK: Log at INFO level and return (caller receives permitted=False).
        LOG: Log at WARNING level and return (caller receives permitted=False).
        """
        if self._config.on_denied == DeniedAction.RAISE:
            raise GovernanceDeniedError(
                subject=tool_name,
                agent_name=agent_name,
                reason=reason,
                decision=decision,
            )
        elif self._config.on_denied == DeniedAction.BLOCK:
            logger.info(
                "ToolGuard: '%s' blocked for agent '%s' (scope='%s'): %s",
                tool_name,
                agent_name,
                scope,
                reason,
            )
        else:
            # DeniedAction.LOG — record and continue
            logger.warning(
                "ToolGuard: '%s' denied for agent '%s' (logged, execution "
                "continues, scope='%s'): %s",
                tool_name,
                agent_name,
                scope,
                reason,
            )

    def _extract_amount(self, args: dict[str, Any]) -> float | None:
        """
        Attempt to extract a spend amount from the tool call arguments.

        Returns None if ``config.amount_field`` is not set or the field is absent.
        Missing amounts are always valid.
        """
        if self._config.amount_field is None:
            return None
        raw = args.get(self._config.amount_field)
        if raw is None:
            return None
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None

    def _write_audit(self, record: AuditRecord) -> None:
        """Write an audit record to the governance engine's audit trail."""
        if hasattr(self._engine, "record_audit_event"):
            self._engine.record_audit_event(
                agent_id=record.agent_name,
                tool_name=record.subject,
                succeeded=record.succeeded,
                error_message=record.error_message,
                output_preview=record.output_preview,
            )
        else:
            logger.debug(
                "Audit: subject='%s' agent='%s' succeeded=%s",
                record.subject,
                record.agent_name,
                record.succeeded,
            )
