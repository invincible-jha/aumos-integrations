# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
AumOSGuardrail — OpenAI Agents SDK governance guardrail.

Implements the guardrail pattern for the OpenAI Agents SDK, checking governance
before and after every tool call that an agent attempts.  The guardrail is a
pure adapter between the OpenAI Agents SDK guardrail interface and the
``aumos-governance`` SDK.

The OpenAI Agents SDK guardrail interface is structural: this module does not
import from ``agents`` (the openai-agents package) directly.  Any agent
framework that exposes a compatible ``before_tool_call`` / ``after_tool_call``
hook will work with this guardrail at runtime.  This keeps the integration
usable across SDK versions.

Governance constraints respected by this module:
- Trust changes are MANUAL ONLY — the guardrail never modifies trust levels.
- Budget allocation is STATIC ONLY — limits come from the engine configuration.
- Audit logging is RECORDING ONLY — the guardrail never interprets audit data.

Usage:

.. code-block:: python

    from openai_agents_aumos import AumOSGuardrail
    from openai_agents_aumos.config import GuardrailConfig

    engine = GovernanceEngine(config)
    guardrail = AumOSGuardrail(engine=engine, agent_id="support-agent")

    # Attach to your OpenAI Agents SDK agent:
    # agent = Agent(name="support", guardrails=[guardrail], ...)
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from .config import GuardrailConfig
from .errors import GovernanceDeniedError
from .protocol import GovernanceEngineProtocol
from .types import AuditRecord, DeniedAction, GuardrailCheckContext, GuardrailResult

logger = logging.getLogger(__name__)

# Maximum characters to include in input preview sent to audit.
_INPUT_PREVIEW_MAX = 256


class AumOSGuardrail:
    """
    OpenAI Agents SDK governance guardrail implementing AumOS governance.

    Attach this guardrail to an OpenAI Agents SDK agent to enforce AumOS
    governance controls on every tool call the agent attempts.

    The guardrail follows the two-hook pattern common to the OpenAI Agents SDK:
    - ``before_tool_call``: evaluates governance; raises or logs on denial.
    - ``after_tool_call``: records the outcome to the append-only audit trail.

    Args:
        engine: An ``aumos-governance`` governance engine instance satisfying
            ``GovernanceEngineProtocol``.
        agent_id: Identifier for the agent this guardrail governs.
        on_denied: Denial handling mode.  Accepts ``'raise'``, ``'skip'``,
            or ``'log'``.  Defaults to ``'raise'``.
        config: Optional fully-specified ``GuardrailConfig``.  When provided,
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
        config: GuardrailConfig | None = None,
    ) -> None:
        self._engine = engine

        if config is not None:
            self._config = config
        else:
            self._config = GuardrailConfig(
                agent_id=agent_id,
                on_denied=DeniedAction(on_denied),
            )

        # Keyed by run_id so parallel tool calls do not interfere.
        self._pending: dict[str, GuardrailCheckContext] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def agent_id(self) -> str:
        """Identifier for the agent this guardrail governs."""
        return self._config.agent_id

    @property
    def on_denied(self) -> DeniedAction:
        """Denial handling mode."""
        return self._config.on_denied

    # ------------------------------------------------------------------
    # OpenAI Agents SDK guardrail hooks
    # ------------------------------------------------------------------

    def before_tool_call(
        self,
        tool_name: str,
        tool_input: Any,
        *,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> GuardrailResult:
        """
        Called before a tool executes.

        Evaluates governance synchronously.  When the evaluation denies the
        call, acts according to the configured ``on_denied`` mode.

        Args:
            tool_name: Name of the tool about to be invoked.
            tool_input: The input arguments for the tool call.
            run_id: Optional run identifier for audit correlation.
            **kwargs: Additional guardrail call keyword arguments (ignored).

        Returns:
            ``GuardrailResult`` with ``permitted=True`` when the call is
            allowed.  When ``on_denied='skip'`` or ``'log'`` and the call is
            denied, returns a result with ``permitted=False``.

        Raises:
            GovernanceDeniedError: When ``on_denied='raise'`` and governance
                denies the call.
        """
        run_id = run_id or str(uuid.uuid4())
        scope = self._config.scope_for_tool(tool_name)
        amount = self._extract_amount(tool_input)
        input_preview = self._preview_input(tool_input)

        context = GuardrailCheckContext(
            tool_name=tool_name,
            agent_id=self._config.agent_id,
            scope=scope,
            input_preview=input_preview,
            amount=amount,
            run_id=run_id,
            extra=kwargs,
        )
        self._pending[run_id] = context

        logger.debug(
            "Evaluating governance for tool '%s' (agent='%s', scope='%s')",
            tool_name,
            self._config.agent_id,
            scope,
        )

        decision = self._engine.evaluate_sync(
            agent_id=self._config.agent_id,
            scope=scope,
            amount=amount,
        )

        permitted = decision.get("permitted", False)
        reason = decision.get("reason") or ""

        if not permitted:
            self._handle_denial(tool_name, reason or "governance policy denied this tool call")

        return GuardrailResult(
            permitted=permitted,
            reason=reason,
            scope=scope,
            agent_id=self._config.agent_id,
        )

    def after_tool_call(
        self,
        tool_name: str,
        tool_output: Any,
        *,
        run_id: str | None = None,
        succeeded: bool = True,
        error_message: str | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Called after a tool completes (successfully or with error).

        Records the outcome to the append-only audit trail when
        ``audit_all_calls`` is enabled.

        Args:
            tool_name: Name of the tool that executed.
            tool_output: The output returned by the tool.
            run_id: Run identifier for correlation with ``before_tool_call``.
            succeeded: ``True`` if the tool completed without error.
            error_message: Error description when ``succeeded`` is ``False``.
            **kwargs: Additional guardrail call keyword arguments (ignored).
        """
        run_id = run_id or ""
        self._pending.pop(run_id, None)

        if not self._config.audit_all_calls:
            return

        output_preview: str | None = None
        if tool_output is not None:
            raw = str(tool_output)
            output_preview = raw[: self._config.audit_output_preview_length] or None

        record = AuditRecord(
            tool_name=tool_name,
            agent_id=self._config.agent_id,
            run_id=run_id or None,
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
        present in a dict representation of ``tool_input``.
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

    def _preview_input(self, tool_input: Any) -> str:
        """
        Produce a truncated string preview of the tool input for audit records.
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
        SKIP: Log at INFO level and return — caller should not execute the tool.
        LOG: Log at WARNING level and return — execution may continue.
        """
        if self._config.on_denied == DeniedAction.RAISE:
            raise GovernanceDeniedError(
                tool_name=tool_name,
                agent_id=self._config.agent_id,
                reason=reason,
            )
        elif self._config.on_denied == DeniedAction.SKIP:
            logger.info(
                "Tool '%s' skipped by governance (agent='%s'): %s",
                tool_name,
                self._config.agent_id,
                reason,
            )
        else:
            # DeniedAction.LOG — record and continue
            logger.warning(
                "Governance denied tool '%s' for agent '%s' "
                "(logged, execution continues): %s",
                tool_name,
                self._config.agent_id,
                reason,
            )

    def _record_audit(self, record: AuditRecord) -> None:
        """
        Write an audit record to the governance engine's append-only audit trail.
        """
        self._engine.record_audit_event(
            agent_id=record.agent_id,
            tool_name=record.tool_name,
            run_id=record.run_id,
            succeeded=record.succeeded,
            error_message=record.error_message,
            output_preview=record.output_preview,
        )
