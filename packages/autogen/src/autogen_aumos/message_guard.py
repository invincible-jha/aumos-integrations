# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
MessageGuard — standalone message governance for AutoGen conversations.

``MessageGuard`` evaluates governance at message-send boundaries. It can be used
standalone (by calling ``check_message`` directly from a reply function or hook)
or via ``GovernedConversableAgent``, which installs it as a message hook.

The guard is a pure checkpoint adapter: it calls ``engine.evaluate_sync()``
with the sender, recipient, and scope, then acts on the returned decision.
It does not inspect message content for policy enforcement — content analysis is
out of scope and would constitute prohibited implementation.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .config import AutoGenGovernanceConfig
from .errors import GovernanceDeniedError, MessageBlockedError
from .types import AuditRecord, DeniedAction, GuardResult, MessageContext

logger = logging.getLogger(__name__)

_BLOCK_MESSAGE = "[governance] message blocked — policy denied this communication"


class MessageGuard:
    """
    Standalone message governance for AutoGen conversations.

    Evaluates a governance checkpoint on every message send between AutoGen
    agents. The check uses the sender name, recipient name, and a governance
    scope derived from the recipient (or the configured default scope).

    Args:
        engine: An initialized ``aumos-governance`` ``GovernanceEngine`` instance.
        config: Optional ``AutoGenGovernanceConfig``. If omitted, defaults are used.

    Example::

        from autogen_aumos import MessageGuard

        guard = MessageGuard(engine=engine)
        result = guard.check_message(
            sender_name="planner",
            recipient_name="executor",
            message="Please run the deployment script.",
        )
        if not result.permitted:
            print(f"Message blocked: {result.reason}")
    """

    def __init__(
        self,
        engine: Any,
        config: Optional[AutoGenGovernanceConfig] = None,
    ) -> None:
        self._engine = engine
        self._config: AutoGenGovernanceConfig = config or AutoGenGovernanceConfig()

    def check_message(
        self,
        sender_name: str,
        recipient_name: str,
        message: str,
    ) -> GuardResult:
        """
        Evaluate governance on a proposed message send.

        Calls ``engine.evaluate_sync()`` with the sender as agent ID and the
        configured scope for the recipient. Returns a ``GuardResult`` describing
        the decision.

        When ``on_denied`` is ``'raise'``, this method raises
        ``GovernanceDeniedError`` on denial instead of returning a result with
        ``permitted=False``.

        When ``on_denied`` is ``'block'``, this method raises
        ``MessageBlockedError`` so that calling code can intercept the message
        and substitute a block notice.

        Args:
            sender_name: Name of the agent sending the message.
            recipient_name: Name of the agent receiving the message.
            message: The message content. A preview (first 256 chars) is used
                in the audit record — the full content is never stored here.

        Returns:
            ``GuardResult`` with ``permitted=True`` if governance allows the
            message, or ``permitted=False`` with a denial reason under ``'log'``
            mode.

        Raises:
            GovernanceDeniedError: When governance denies and ``on_denied='raise'``.
            MessageBlockedError: When governance denies and ``on_denied='block'``.
        """
        scope = self._config.scope_for_message(recipient_name)
        context = MessageContext(
            sender_name=sender_name,
            recipient_name=recipient_name,
            message_preview=message[:256],
            scope=scope,
        )
        decision = self._evaluate(context)
        permitted = self._is_allowed(decision)

        if not permitted:
            reason = self._extract_reason(decision)
            self._handle_denial(
                sender_name=sender_name,
                recipient_name=recipient_name,
                scope=scope,
                reason=reason,
                decision=decision,
            )
            # Only reached under LOG mode
            self._write_audit(
                AuditRecord(
                    subject="message",
                    agent_name=sender_name,
                    succeeded=False,
                    error_message=reason,
                )
            )
            return GuardResult(
                permitted=False,
                reason=reason,
                scope=scope,
                agent_name=sender_name,
            )

        if self._config.audit_all_actions:
            self._write_audit(
                AuditRecord(
                    subject="message",
                    agent_name=sender_name,
                    succeeded=True,
                )
            )
        return GuardResult(
            permitted=True,
            reason="",
            scope=scope,
            agent_name=sender_name,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evaluate(self, context: MessageContext) -> Any:
        """Submit a synchronous governance evaluation for the message context."""
        return self._engine.evaluate_sync(
            agent_id=context.sender_name,
            scope=context.scope,
        )

    def _is_allowed(self, decision: Any) -> bool:
        """Return True if the governance decision permits the message."""
        if hasattr(decision, "allowed"):
            return bool(decision.allowed)
        return bool(decision)

    def _extract_reason(self, decision: Any) -> str:
        """Return a human-readable denial reason from the governance decision."""
        if hasattr(decision, "reason") and decision.reason:
            return str(decision.reason)
        return "governance policy denied this message"

    def _handle_denial(
        self,
        sender_name: str,
        recipient_name: str,
        scope: str,
        reason: str,
        decision: Any,
    ) -> None:
        """
        Act on a denial according to the configured ``on_denied`` mode.

        RAISE: Raise ``GovernanceDeniedError``.
        BLOCK: Raise ``MessageBlockedError`` (caller substitutes a block notice).
        LOG: Log at WARNING level and return.
        """
        if self._config.on_denied == DeniedAction.RAISE:
            raise GovernanceDeniedError(
                subject=f"message_to_{recipient_name}",
                agent_name=sender_name,
                reason=reason,
                decision=decision,
            )
        elif self._config.on_denied == DeniedAction.BLOCK:
            logger.info(
                "MessageGuard: message from '%s' to '%s' blocked (scope='%s'): %s",
                sender_name,
                recipient_name,
                scope,
                reason,
            )
            raise MessageBlockedError(
                sender_name=sender_name,
                recipient_name=recipient_name,
                reason=reason,
            )
        else:
            # DeniedAction.LOG — record and continue
            logger.warning(
                "MessageGuard: message from '%s' to '%s' denied (logged, "
                "execution continues, scope='%s'): %s",
                sender_name,
                recipient_name,
                scope,
                reason,
            )

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
