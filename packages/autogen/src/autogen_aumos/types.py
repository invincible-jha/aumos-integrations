# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Integration-specific types for autogen-aumos.

These types describe data flowing through the AutoGen governance integration
layer. They are adapter types that translate AutoGen message and function-call
payloads into governance evaluation inputs, and relay governance outcomes back
to AutoGen conversation flow.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DeniedAction(str, Enum):
    """
    What the integration does when a governance evaluation returns a denial.

    RAISE: Raise ``GovernanceDeniedError``. The conversation or function call fails.
    BLOCK: Return a denial message as the message or function output. The
        conversation continues with the blocked message visible to the agent.
    LOG: Log the denial and allow execution to proceed regardless.
    """

    RAISE = "raise"
    BLOCK = "block"
    LOG = "log"


class MessageContext(BaseModel):
    """
    Contextual information extracted from an AutoGen message send event.

    Built inside ``MessageGuard.check_message()`` and used to construct the
    governance evaluation request.
    """

    sender_name: str = Field(description="Name of the agent sending the message.")
    recipient_name: str = Field(description="Name of the agent receiving the message.")
    message_preview: str = Field(
        description="Truncated preview of the message content for audit purposes."
    )
    scope: str = Field(description="Governance scope for this message send.")
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata from the AutoGen message payload.",
    )


class ToolCallContext(BaseModel):
    """
    Contextual information for a governed AutoGen function/tool execution event.

    Built inside ``ToolGuard.check_tool()`` before governance is evaluated.
    """

    agent_name: str = Field(description="Name of the agent invoking the tool.")
    tool_name: str = Field(description="Name of the tool or function being called.")
    scope: str = Field(description="Governance scope for this tool call.")
    args: dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments passed to the function call.",
    )
    amount: float | None = Field(
        default=None,
        description=(
            "Optional spend amount extracted from call arguments. "
            "Present only when an amount_field is configured."
        ),
    )


class GuardResult(BaseModel):
    """
    The outcome of a governance guard check performed by ``MessageGuard`` or
    ``ToolGuard``.

    This summary type is returned to the caller so that AutoGen integration
    code does not need to import directly from ``aumos-governance``.
    """

    permitted: bool = Field(description="True if governance allows the action.")
    reason: str = Field(
        default="",
        description="Human-readable reason provided with a denial. Empty on permit.",
    )
    scope: str = Field(description="Governance scope that was evaluated.")
    agent_name: str = Field(description="Name of the agent that triggered the evaluation.")


class AuditRecord(BaseModel):
    """
    A record of a completed (or denied) message send or function call written
    to the audit trail.

    Sent to ``engine.record_audit_event()`` after each governance check.
    """

    subject: str = Field(
        description="The tool name or 'message' identifier for what was audited."
    )
    agent_name: str = Field(description="Name of the agent that triggered the event.")
    succeeded: bool = Field(
        description="True if the action completed without error or denial."
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if the action was denied or raised an exception.",
    )
    output_preview: str | None = Field(
        default=None,
        description=(
            "Truncated preview of the output for audit purposes. "
            "Maximum 256 characters."
        ),
    )
