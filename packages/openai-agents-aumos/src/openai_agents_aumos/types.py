# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Integration-specific types for openai-agents-aumos.

These types describe data flowing through the OpenAI Agents SDK governance
integration layer.  They are adapter types that translate OpenAI Agents SDK
tool-call payloads into governance evaluation inputs, and relay governance
outcomes back to the guardrail interface.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DeniedAction(str, Enum):
    """
    What the integration does when a governance evaluation returns a denial.

    RAISE: Raise ``GovernanceDeniedError``. The tool invocation fails.
    SKIP: Return a denial message string as the guardrail output. The agent
        run continues with the denial visible in the output.
    LOG: Log the denial at WARNING level and allow execution to proceed.
    """

    RAISE = "raise"
    SKIP = "skip"
    LOG = "log"


class GuardrailCheckContext(BaseModel):
    """
    Contextual information for a governed OpenAI Agents SDK tool call.

    Built inside ``AumOSGuardrail.before_tool_call()`` and used to construct
    the governance evaluation request.
    """

    tool_name: str = Field(description="Name of the tool being checked.")
    agent_id: str = Field(description="Identifier for the agent making the call.")
    scope: str = Field(description="Governance scope inferred from the tool name.")
    input_preview: str = Field(
        description=(
            "Truncated preview of the tool input arguments. "
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
    run_id: str | None = Field(
        default=None,
        description="Optional run identifier for correlation with audit records.",
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata from the guardrail call payload.",
    )


class GuardrailResult(BaseModel):
    """
    The outcome of a governance guardrail check performed by ``AumOSGuardrail``.

    Returned to the caller so that guardrail code does not need to import
    directly from ``aumos-governance``.
    """

    permitted: bool = Field(description="True if governance allows the tool call.")
    reason: str = Field(
        default="",
        description="Human-readable reason provided with a denial. Empty on permit.",
    )
    scope: str = Field(description="Governance scope that was evaluated.")
    agent_id: str = Field(description="Agent that triggered the evaluation.")


class AuditRecord(BaseModel):
    """
    A record of a completed (or denied) tool execution written to the audit trail.

    Sent to ``engine.record_audit_event()`` after each tool invocation.
    """

    tool_name: str = Field(description="Name of the tool that executed.")
    agent_id: str = Field(description="Identifier for the agent.")
    run_id: str | None = Field(
        default=None,
        description="Optional run identifier for correlation.",
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
