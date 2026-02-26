# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Integration-specific exceptions for autogen-aumos.

These exceptions surface governance decisions as standard Python exceptions so
that callers can catch and handle them without importing from aumos-governance
directly.
"""

from __future__ import annotations

from typing import Any


class GovernanceDeniedError(Exception):
    """
    Raised when a governance evaluation returns a denial and ``on_denied`` is set
    to ``'raise'``.

    Attributes:
        subject: The name of the function, tool, or action that was denied.
        agent_name: The name of the agent that triggered the evaluation.
        reason: Human-readable reason from the governance decision.
        decision: The raw governance decision object returned by the engine.
    """

    def __init__(
        self,
        subject: str,
        agent_name: str,
        reason: str,
        decision: Any,
    ) -> None:
        self.subject = subject
        self.agent_name = agent_name
        self.reason = reason
        self.decision = decision
        super().__init__(
            f"Governance denied '{subject}' for agent '{agent_name}': {reason}"
        )


class MessageBlockedError(Exception):
    """
    Raised internally to signal that a message was blocked due to a denial when
    ``on_denied`` is set to ``'block'``.

    This exception may be caught by calling code that needs to distinguish
    between a hard governance failure (``GovernanceDeniedError``) and a soft
    block where the message is replaced by a denial notice.

    Attributes:
        sender_name: Name of the sending agent.
        recipient_name: Name of the intended recipient.
        reason: Human-readable reason from the governance decision.
    """

    def __init__(
        self,
        sender_name: str,
        recipient_name: str,
        reason: str,
    ) -> None:
        self.sender_name = sender_name
        self.recipient_name = recipient_name
        self.reason = reason
        super().__init__(
            f"Message from '{sender_name}' to '{recipient_name}' blocked by governance: "
            f"{reason}"
        )
