# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Integration-specific types for langchain-aumos.

These types describe the shape of data flowing through the integration layer.
They are distinct from aumos-governance SDK types — they are adapter types that
translate LangChain callback payloads into governance evaluation inputs.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DeniedAction(str, Enum):
    """
    What the callback does when a governance evaluation returns a denial.

    RAISE: Raise ``GovernanceDeniedError``. The agent run fails.
    SKIP: Silently return a denial message as the tool output. The agent continues.
    LOG: Log the denial and allow execution to proceed regardless.
    """

    RAISE = "raise"
    SKIP = "skip"
    LOG = "log"


class ToolCallContext(BaseModel):
    """
    Contextual information extracted from a LangChain tool-start callback payload.

    This is assembled inside ``AumOSGovernanceCallback.on_tool_start`` and used
    to build the governance evaluation request.
    """

    tool_name: str = Field(description="Name of the tool being called.")
    agent_id: str = Field(description="Agent identifier for this run.")
    scope: str = Field(
        description="Governance scope inferred from the tool name."
    )
    input_str: str = Field(
        description="Raw input string passed to the tool by the agent."
    )
    amount: float | None = Field(
        default=None,
        description=(
            "Optional spend amount extracted from tool input. "
            "Present only when the tool maps to a budget category."
        ),
    )
    run_id: str | None = Field(
        default=None,
        description="LangChain run ID for correlation with audit trail.",
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata from the LangChain callback kwargs.",
    )


class AuditRecord(BaseModel):
    """
    A record of a completed (or failed) tool execution written to the audit trail.

    Sent to ``engine.record_audit_event()`` after each tool end or tool error.
    """

    tool_name: str = Field(description="Name of the tool that executed.")
    agent_id: str = Field(description="Agent identifier for this run.")
    run_id: str | None = Field(
        default=None,
        description="LangChain run ID for correlation.",
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
