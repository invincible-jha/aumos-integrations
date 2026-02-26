# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
AumOSGovernanceCallback — LangChain BaseCallbackHandler that enforces AumOS
governance on every tool call an agent attempts.

Attach this callback to any LangChain agent or executor via the ``callbacks``
parameter. It intercepts ``on_tool_start``, evaluates the call against the
governance engine, and either allows or denies execution before the tool runs.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Union
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

from .config import GovernanceConfig
from .errors import GovernanceDeniedError, ToolSkippedError
from .types import AuditRecord, DeniedAction, ToolCallContext

logger = logging.getLogger(__name__)


class AumOSGovernanceCallback(BaseCallbackHandler):
    """
    LangChain callback enforcing AumOS governance on tool calls.

    This callback intercepts every tool invocation and submits it for governance
    evaluation before execution is allowed to proceed. The governance engine is
    supplied by the caller — this class is a pure adapter between LangChain's
    callback system and the ``aumos-governance`` SDK.

    Usage (3 lines):

    .. code-block:: python

        engine = GovernanceEngine(config)
        callback = AumOSGovernanceCallback(engine)
        agent = create_agent(llm, tools, callbacks=[callback])

    Args:
        engine: An initialized ``aumos-governance`` ``GovernanceEngine`` instance.
        agent_id: Identifier for the agent this callback governs. Defaults to
            ``'default'``.
        on_denied: What to do when a tool call is denied. Accepts ``'raise'``,
            ``'skip'``, or ``'log'`` (or the equivalent ``DeniedAction`` enum
            value). Defaults to ``'raise'``.
        config: Optional fully-specified ``GovernanceConfig``. When provided,
            ``agent_id`` and ``on_denied`` arguments are ignored in favour of
            the config values.

    Raises:
        GovernanceDeniedError: When ``on_denied='raise'`` and the engine denies a
            tool call.
    """

    def __init__(
        self,
        engine: Any,
        agent_id: str = "default",
        on_denied: Union[DeniedAction, str] = DeniedAction.RAISE,
        config: GovernanceConfig | None = None,
    ) -> None:
        super().__init__()
        self._engine = engine

        if config is not None:
            self._config = config
        else:
            self._config = GovernanceConfig(
                agent_id=agent_id,
                on_denied=on_denied,
            )

        # State shared between on_tool_start and on_tool_end/on_tool_error.
        # Keyed by the LangChain run_id string so parallel tool calls are safe.
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
    # LangChain callback hooks
    # ------------------------------------------------------------------

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Called by LangChain immediately before a tool executes.

        Extracts the tool name and scope, submits a synchronous governance
        evaluation, and either allows execution to continue or handles the
        denial according to ``on_denied``.

        Args:
            serialized: LangChain serialized tool metadata. Contains ``'name'``
                at minimum.
            input_str: The raw input string the agent is passing to the tool.
            run_id: LangChain run identifier for this tool invocation.
            **kwargs: Additional LangChain callback kwargs (ignored).

        Raises:
            GovernanceDeniedError: If the governance decision is a denial and
                ``on_denied`` is ``DeniedAction.RAISE``.
        """
        tool_name: str = serialized.get("name", "unknown_tool")
        scope = self._config.scope_for_tool(tool_name)
        amount = self._extract_amount(input_str)
        run_id_str = str(run_id) if run_id is not None else str(uuid.uuid4())

        context = ToolCallContext(
            tool_name=tool_name,
            agent_id=self._config.agent_id,
            scope=scope,
            input_str=input_str,
            amount=amount,
            run_id=run_id_str,
            extra=kwargs,
        )
        self._pending[run_id_str] = context

        logger.debug(
            "Evaluating governance for tool '%s' (agent='%s', scope='%s')",
            tool_name,
            self._config.agent_id,
            scope,
        )

        decision = self._evaluate(context)

        if not self._is_allowed(decision):
            reason = self._extract_reason(decision)
            self._handle_denial(tool_name, reason, decision)

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Called by LangChain after a tool completes successfully.

        Records a successful execution in the audit trail when
        ``audit_all_calls`` is enabled.

        Args:
            output: The string output returned by the tool.
            run_id: LangChain run identifier, used to correlate with the
                context recorded in ``on_tool_start``.
            **kwargs: Additional LangChain callback kwargs (ignored).
        """
        run_id_str = str(run_id) if run_id is not None else None
        context = self._pending.pop(run_id_str or "", None)

        if not self._config.audit_all_calls:
            return

        preview_length = self._config.audit_output_preview_length
        output_preview: str | None = None
        if preview_length > 0:
            output_preview = output[:preview_length] if output else None

        record = AuditRecord(
            tool_name=context.tool_name if context else "unknown_tool",
            agent_id=self._config.agent_id,
            run_id=run_id_str,
            succeeded=True,
            output_preview=output_preview,
        )
        self._record_audit(record)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Called by LangChain when a tool raises an exception.

        Records the error in the audit trail so that post-hoc review can
        identify which tool calls failed and why.

        Args:
            error: The exception raised by the tool.
            run_id: LangChain run identifier, used to correlate with the
                context recorded in ``on_tool_start``.
            **kwargs: Additional LangChain callback kwargs (ignored).
        """
        run_id_str = str(run_id) if run_id is not None else None
        context = self._pending.pop(run_id_str or "", None)

        record = AuditRecord(
            tool_name=context.tool_name if context else "unknown_tool",
            agent_id=self._config.agent_id,
            run_id=run_id_str,
            succeeded=False,
            error_message=str(error),
        )
        self._record_audit(record)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_amount(self, input_str: str) -> float | None:
        """
        Attempt to parse a spend amount from the tool input string.

        Returns the amount if ``config.amount_field`` is set and the field is
        present in a JSON-decoded version of ``input_str``. Returns ``None``
        otherwise — missing amounts are valid and mean no spend tracking.
        """
        if self._config.amount_field is None:
            return None
        try:
            parsed = json.loads(input_str)
            if isinstance(parsed, dict):
                raw = parsed.get(self._config.amount_field)
                if raw is not None:
                    return float(raw)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        return None

    def _evaluate(self, context: ToolCallContext) -> Any:
        """
        Submit a synchronous governance evaluation for the given tool call context.

        Delegates to ``engine.evaluate_sync()``. The engine is caller-supplied;
        this method does not interpret the decision beyond calling
        ``_is_allowed()``.
        """
        return self._engine.evaluate_sync(
            agent_id=context.agent_id,
            scope=context.scope,
            amount=context.amount,
        )

    def _is_allowed(self, decision: Any) -> bool:
        """
        Return True if the governance decision permits the tool call.

        Reads ``decision.allowed`` if present; falls back to treating the
        decision as truthy. This accommodates different versions of the
        aumos-governance SDK that may use different decision shapes.
        """
        if hasattr(decision, "allowed"):
            return bool(decision.allowed)
        return bool(decision)

    def _extract_reason(self, decision: Any) -> str:
        """Return a human-readable denial reason from the governance decision."""
        if hasattr(decision, "reason") and decision.reason:
            return str(decision.reason)
        return "governance policy denied this tool call"

    def _handle_denial(
        self, tool_name: str, reason: str, decision: Any
    ) -> None:
        """
        Act on a denial according to the configured ``on_denied`` mode.

        RAISE: Raise ``GovernanceDeniedError``.
        SKIP: Raise ``ToolSkippedError`` (caught higher up, converted to a skip message).
        LOG: Log at WARNING level and return, allowing execution to continue.
        """
        if self._config.on_denied == DeniedAction.RAISE:
            raise GovernanceDeniedError(
                tool_name=tool_name,
                agent_id=self._config.agent_id,
                reason=reason,
                decision=decision,
            )
        elif self._config.on_denied == DeniedAction.SKIP:
            logger.info(
                "Tool '%s' skipped by governance (agent='%s'): %s",
                tool_name,
                self._config.agent_id,
                reason,
            )
            raise ToolSkippedError(tool_name=tool_name, reason=reason)
        else:
            # DeniedAction.LOG — record and continue
            logger.warning(
                "Governance denied tool '%s' for agent '%s' (logged, execution continues): %s",
                tool_name,
                self._config.agent_id,
                reason,
            )

    def _record_audit(self, record: AuditRecord) -> None:
        """
        Write an audit record to the governance engine's audit trail.

        Uses ``engine.record_audit_event()`` if available. Falls back to a
        warning log so that engines without an audit API do not break the
        integration.
        """
        if hasattr(self._engine, "record_audit_event"):
            self._engine.record_audit_event(
                agent_id=record.agent_id,
                tool_name=record.tool_name,
                run_id=record.run_id,
                succeeded=record.succeeded,
                error_message=record.error_message,
                output_preview=record.output_preview,
            )
        else:
            logger.debug(
                "Audit: tool='%s' agent='%s' succeeded=%s",
                record.tool_name,
                record.agent_id,
                record.succeeded,
            )
