# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Integration-specific types for crewai-aumos.

These types describe data flowing through the CrewAI governance integration layer.
They are adapter types that translate CrewAI task and tool payloads into
governance evaluation inputs, and relay governance outcomes back to CrewAI execution.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DeniedAction(str, Enum):
    """
    What the integration does when a governance evaluation returns a denial.

    RAISE: Raise ``GovernanceDeniedError``. The task or crew run fails.
    SKIP: Return a denial message string. The crew continues with the next task.
    LOG: Log the denial and allow execution to proceed regardless.
    """

    RAISE = "raise"
    SKIP = "skip"
    LOG = "log"


class TaskContext(BaseModel):
    """
    Contextual information extracted from a CrewAI task at governance check time.

    Built inside ``TaskGuard.guard_task()`` and used to construct the
    governance evaluation request.
    """

    task_description: str = Field(description="Description of the task being checked.")
    agent_role: str = Field(description="Role identifier of the agent executing the task.")
    scope: str = Field(description="Governance scope inferred for this task.")
    expected_output: str | None = Field(
        default=None,
        description="Optional expected output description from the task definition.",
    )
    tools: list[str] = Field(
        default_factory=list,
        description="Names of tools assigned to this task.",
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata from the CrewAI task object.",
    )


class ToolCallContext(BaseModel):
    """
    Contextual information for a governed CrewAI tool call.

    Built inside ``GovernedCrewTool.run()`` before governance is evaluated.
    """

    tool_name: str = Field(description="Name of the tool being called.")
    agent_role: str = Field(description="Role identifier of the agent calling the tool.")
    scope: str = Field(description="Governance scope for this tool call.")
    serialized_input: str = Field(
        description="Serialized representation of the tool input arguments."
    )
    amount: float | None = Field(
        default=None,
        description=(
            "Optional spend amount extracted from tool input. "
            "Present only when the tool maps to a budget category."
        ),
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata.",
    )


class GuardResult(BaseModel):
    """
    The outcome of a governance guard check performed by ``TaskGuard`` or
    ``GovernedCrewTool``.

    This is a summary type returned to the caller so that CrewAI integration
    code does not need to import directly from ``aumos-governance``.
    """

    permitted: bool = Field(description="True if governance allows the action.")
    reason: str = Field(
        default="",
        description="Human-readable reason provided with a denial. Empty on permit.",
    )
    scope: str = Field(description="Governance scope that was evaluated.")
    agent_role: str = Field(description="Agent role that triggered the evaluation.")


class AuditRecord(BaseModel):
    """
    A record of a completed (or denied) tool execution written to the audit trail.

    Sent to ``engine.record_audit_event()`` after each tool invocation.
    """

    tool_name: str = Field(description="Name of the tool that executed.")
    agent_role: str = Field(description="Role identifier of the executing agent.")
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
