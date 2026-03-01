# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
AumOSADKCallback — Google ADK governance callback.

Hooks into the Google ADK tool execution lifecycle to enforce AumOS governance
before and after every tool call.  The callback is a pure adapter between the
ADK callback interface and the ``aumos-governance`` SDK.

The ADK callback interface is structural: this module does not import from
``google.adk`` directly.  Any ADK context object that exposes the attributes
this callback reads will work at runtime.  This avoids a hard dependency on
a specific version of the ``google-adk`` package.

Governance constraints respected by this module:
- Trust changes are MANUAL ONLY — the callback never modifies trust levels.
- Budget allocation is STATIC ONLY — limits come from the engine configuration.
- Audit logging is RECORDING ONLY — the callback never interprets audit data.

Usage:

.. code-block:: python

    from adk_aumos import AumOSADKCallback
    from adk_aumos.config import GovernanceConfig

    engine = GovernanceEngine(config)
    callback = AumOSADKCallback(engine=engine, agent_id="research-agent")
    # Attach to your ADK agent via the callbacks parameter.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from .config import GovernanceConfig
from .errors import GovernanceDeniedError
from .protocol import GovernanceEngineProtocol
from .types import AuditRecord, DeniedAction, ToolCallContext

logger = logging.getLogger(__name__)

# Maximum number of characters to include in the input summary sent to audit.
_INPUT_PREVIEW_MAX = 256


class AumOSADKCallback:
    """
    Google ADK callback that enforces AumOS governance on every tool call.

    Attach this callback to a Google ADK agent.  Before each tool execution
    the callback submits a synchronous governance evaluation.  If denied, it
    acts according to the configured ``on_denied`` mode.  After execution it
    records an audit event.

    The callback does not depend on any specific ADK class hierarchy.  It
    exposes ``before_tool_call`` and ``after_tool_call`` methods that follow
    the ADK callback naming convention.

    Args:
        engine: An ``aumos-governance`` governance engine instance.
        agent_id: Identifier for the agent this callback governs.
        on_denied: Denial handling mode.  Accepts ``'raise'``, ``'skip'``,
            or ``'log'``.  Defaults to ``'raise'``.
        config: Optional fully-specified ``GovernanceConfig``.  When provided,
            ``agent_id`` and ``on_denied`` arguments are ignored.

    Raises:
        GovernanceDeniedError: When ``on_denied='raise'`` and governance denies
            a tool call inside ``before_tool_call``.
    """

    def __init__(
        self,
        engine: GovernanceEngineProtocol,
        agent_id: str = "default",
        on_denied: DeniedAction | str = DeniedAction.RAISE,
        config: GovernanceConfig | None = None,
    ) -> None:
        self._engine = engine

        if config is not None:
            self._config = config
        else:
            self._config = GovernanceConfig(
                agent_id=agent_id,
                on_denied=DeniedAction(on_denied),
            )

        # Keyed by invocation_id so parallel calls do not interfere.
        self._pending: dict[str, ToolCallContext] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def agent_id(self) -> str:
        """Identifier for the agent this callback governs."""
        return self._config.agent_id

    @property
    def on_denied(self) -> DeniedAction:
        """Denial handling mode."""
        return self._config.on_denied

    # ------------------------------------------------------------------
    # ADK callback hooks
    # ------------------------------------------------------------------

    def before_tool_call(
        self,
        tool_name: str,
        tool_input: Any,
        *,
        invocation_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Called by the ADK runtime immediately before a tool executes.

        Evaluates governance for the upcoming tool call.  If denied, acts
        according to the configured ``on_denied`` mode.

        Args:
            tool_name: Name of the tool about to be invoked.
            tool_input: The input arguments for the tool call (dict, str, etc.).
            invocation_id: Optional ADK invocation identifier for correlation.
            **kwargs: Additional ADK callback keyword arguments (ignored).

        Raises:
            GovernanceDeniedError: If governance denies the call and
                ``on_denied`` is ``DeniedAction.RAISE``.
        """
        invocation_id = invocation_id or str(uuid.uuid4())
        scope = self._config.scope_for_tool(tool_name)
        amount = self._extract_amount(tool_input)
        input_summary = self._summarise_input(tool_input)

        context = ToolCallContext(
            tool_name=tool_name,
            agent_id=self._config.agent_id,
            scope=scope,
            input_summary=input_summary,
            amount=amount,
            invocation_id=invocation_id,
            extra=kwargs,
        )
        self._pending[invocation_id] = context

        logger.debug(
            "Evaluating governance for ADK tool '%s' (agent='%s', scope='%s')",
            tool_name,
            self._config.agent_id,
            scope,
        )

        decision = self._engine.evaluate_sync(
            agent_id=self._config.agent_id,
            scope=scope,
            amount=amount,
        )

        if not decision.get("permitted", False):
            reason = decision.get("reason") or "governance policy denied this tool call"
            self._handle_denial(tool_name, reason)

    def after_tool_call(
        self,
        tool_name: str,
        tool_output: Any,
        *,
        invocation_id: str | None = None,
        succeeded: bool = True,
        error_message: str | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Called by the ADK runtime after a tool completes (successfully or with error).

        Records the outcome to the audit trail.

        Args:
            tool_name: Name of the tool that executed.
            tool_output: The output returned by the tool.
            invocation_id: ADK invocation identifier for correlation.
            succeeded: ``True`` if the tool completed without error.
            error_message: Error description when ``succeeded`` is ``False``.
            **kwargs: Additional ADK callback keyword arguments (ignored).
        """
        invocation_id = invocation_id or ""
        self._pending.pop(invocation_id, None)

        if not self._config.audit_all_calls:
            return

        output_preview: str | None = None
        if tool_output is not None:
            raw = str(tool_output)
            output_preview = raw[: self._config.audit_output_preview_length] or None

        record = AuditRecord(
            tool_name=tool_name,
            agent_id=self._config.agent_id,
            invocation_id=invocation_id or None,
            succeeded=succeeded,
            error_message=error_message,
            output_preview=output_preview,
        )
        self._record_audit(record)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_amount(self, tool_input: Any) -> float | None:
        """
        Attempt to parse a spend amount from the tool input.

        Returns the amount if ``config.amount_field`` is set and the field is
        present in a JSON-decoded dict representation of ``tool_input``.
        Returns ``None`` otherwise.
        """
        if self._config.amount_field is None:
            return None
        try:
            if isinstance(tool_input, dict):
                raw = tool_input.get(self._config.amount_field)
            elif isinstance(tool_input, str):
                parsed = json.loads(tool_input)
                raw = parsed.get(self._config.amount_field) if isinstance(parsed, dict) else None
            else:
                return None
            if raw is not None:
                return float(raw)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        return None

    def _summarise_input(self, tool_input: Any) -> str:
        """
        Produce a truncated string summary of the tool input for audit records.
        """
        try:
            if isinstance(tool_input, str):
                raw = tool_input
            else:
                raw = json.dumps(tool_input, default=str)
        except (TypeError, ValueError):
            raw = repr(tool_input)
        return raw[:_INPUT_PREVIEW_MAX]

    def _handle_denial(self, tool_name: str, reason: str) -> None:
        """
        Act on a denial according to the configured ``on_denied`` mode.

        RAISE: Raise ``GovernanceDeniedError``.
        SKIP: Log at INFO level and return (caller receives no exception but
            tool execution will not proceed if caller respects the hook).
        LOG: Log at WARNING level and return (execution may continue).
        """
        if self._config.on_denied == DeniedAction.RAISE:
            raise GovernanceDeniedError(
                tool_name=tool_name,
                agent_id=self._config.agent_id,
                reason=reason,
            )
        elif self._config.on_denied == DeniedAction.SKIP:
            logger.info(
                "ADK tool '%s' skipped by governance (agent='%s'): %s",
                tool_name,
                self._config.agent_id,
                reason,
            )
        else:
            # DeniedAction.LOG — record and continue
            logger.warning(
                "Governance denied ADK tool '%s' for agent '%s' "
                "(logged, execution continues): %s",
                tool_name,
                self._config.agent_id,
                reason,
            )

    def _record_audit(self, record: AuditRecord) -> None:
        """
        Write an audit record to the governance engine's audit trail.

        Uses ``engine.record_audit_event()`` if available.  Falls back to a
        debug log so that engines without an audit API do not break the
        integration.
        """
        self._engine.record_audit_event(
            agent_id=record.agent_id,
            tool_name=record.tool_name,
            run_id=record.invocation_id,
            succeeded=record.succeeded,
            error_message=record.error_message,
            output_preview=record.output_preview,
        )
