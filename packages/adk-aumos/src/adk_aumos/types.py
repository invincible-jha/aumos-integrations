# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Integration-specific types for adk-aumos.

These types describe data flowing through the Google ADK governance integration
layer.  They are adapter types that translate ADK callback payloads into
governance evaluation inputs, and relay governance outcomes back to ADK
execution hooks.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DeniedAction(str, Enum):
    """
    What the integration does when a governance evaluation returns a denial.

    RAISE: Raise ``GovernanceDeniedError``. The tool invocation fails and the
        ADK agent will see an exception.
    SKIP: Return a denial message string as the tool result. The ADK agent
        continues with the denial message as the tool output.
    LOG: Log the denial at WARNING level and allow execution to proceed.
    """

    RAISE = "raise"
    SKIP = "skip"
    LOG = "log"


class ToolCallContext(BaseModel):
    """
    Contextual information extracted from a Google ADK tool invocation event.

    Built inside ``AumOSADKCallback.before_tool_call()`` and used to construct
    the governance evaluation request.
    """

    tool_name: str = Field(description="Name of the tool being invoked.")
    agent_id: str = Field(description="Identifier for the ADK agent making the call.")
    scope: str = Field(
        description="Governance scope inferred from the tool name."
    )
    input_summary: str = Field(
        description=(
            "Truncated summary of the tool input arguments for audit purposes. "
            "Maximum 256 characters."
        )
    )
    amount: float | None = Field(
        default=None,
        description=(
            "Optional spend amount extracted from tool input. "
            "Present only when the tool maps to a budget category."
        ),
    )
    invocation_id: str | None = Field(
        default=None,
        description="ADK invocation ID for correlation with audit trail.",
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata from the ADK callback payload.",
    )


class AuditRecord(BaseModel):
    """
    A record of a completed (or failed) ADK tool invocation written to the
    audit trail.

    Sent to ``engine.record_audit_event()`` after each tool completion or error.
    """

    tool_name: str = Field(description="Name of the tool that executed.")
    agent_id: str = Field(description="Identifier for the ADK agent.")
    invocation_id: str | None = Field(
        default=None,
        description="ADK invocation ID for correlation.",
    )
    succeeded: bool = Field(
        description="True if the tool completed without error, False otherwise."
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if the tool raised an exception.",
    )
    output_preview: str | None = Field(
        default=None,
        description=(
            "Truncated preview of the tool output for audit purposes. "
            "Maximum 256 characters."
        ),
    )
