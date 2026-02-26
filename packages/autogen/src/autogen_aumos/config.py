# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Configuration for autogen-aumos integration.

All runtime behaviour of the integration is controlled through
``AutoGenGovernanceConfig``. Values are validated at construction time via
Pydantic v2 — errors surface before any conversation begins.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field, model_validator

from .types import DeniedAction


class AutoGenGovernanceConfig(BaseModel):
    """
    Configuration for the AumOS governance integration with Microsoft AutoGen.

    Pass an instance of this to ``GovernedConversableAgent``, ``MessageGuard``,
    or ``ToolGuard`` to control how governance decisions affect conversation
    and function-call behaviour.

    Attributes:
        on_denied: What to do when a governance evaluation returns a denial.
            ``'raise'`` — raise ``GovernanceDeniedError`` (default).
            ``'block'`` — return the denial message as output; conversation continues.
            ``'log'`` — log the denial and allow execution to proceed.
        default_message_scope: Governance scope used for message-send evaluations
            when no recipient-specific override exists in ``recipient_scope_mapping``.
            Defaults to ``'autogen_message'``.
        recipient_scope_mapping: Optional mapping from recipient agent name to
            governance scope string. If a recipient name is present here, its
            mapped scope is used instead of ``default_message_scope``.
        default_tool_scope: Governance scope used for function/tool calls whose
            name does not appear in ``tool_scope_mapping``.
            Defaults to ``'autogen_tool_call'``.
        tool_scope_mapping: Optional mapping from function/tool name to governance
            scope string.
        amount_field: If set, the integration will attempt to extract this field
            name from tool call arguments and pass it as the spend amount to the
            governance evaluation. If the field is absent, the amount is omitted.
        audit_all_actions: When True, record an audit event for every completed
            message send and function call (both allowed and denied). When False,
            only denied actions are audited. Defaults to True.
        audit_output_preview_length: Maximum number of characters of output to
            include in the audit record. Set to 0 to omit output previews.
            Defaults to 256.
        govern_messages: When True, message sends are evaluated against the
            governance engine. Defaults to True.
        govern_tools: When True, function/tool calls are evaluated against the
            governance engine. Defaults to True.
    """

    on_denied: DeniedAction = Field(
        default=DeniedAction.RAISE,
        description="Action to take when governance denies a message or tool call.",
    )
    default_message_scope: str = Field(
        default="autogen_message",
        min_length=1,
        description="Governance scope used for message sends without a recipient mapping.",
    )
    recipient_scope_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Optional per-recipient governance scope overrides for messages.",
    )
    default_tool_scope: str = Field(
        default="autogen_tool_call",
        min_length=1,
        description="Governance scope used for tool calls without a name mapping.",
    )
    tool_scope_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Optional per-tool governance scope overrides.",
    )
    amount_field: str | None = Field(
        default=None,
        description=(
            "Argument field name to extract as the spend amount from tool calls. "
            "Omit if the tools do not carry spend amounts."
        ),
    )
    audit_all_actions: bool = Field(
        default=True,
        description="Record an audit event for every message send and tool call.",
    )
    audit_output_preview_length: Annotated[int, Field(ge=0, le=4096)] = Field(
        default=256,
        description="Maximum characters of output included in audit records.",
    )
    govern_messages: bool = Field(
        default=True,
        description="Evaluate governance on message sends.",
    )
    govern_tools: bool = Field(
        default=True,
        description="Evaluate governance on function/tool calls.",
    )

    model_config = {"frozen": True}

    @model_validator(mode="before")
    @classmethod
    def coerce_on_denied(cls, values: Any) -> Any:
        """Accept plain strings for on_denied in addition to the enum."""
        if isinstance(values, dict) and isinstance(values.get("on_denied"), str):
            values["on_denied"] = DeniedAction(values["on_denied"])
        return values

    def scope_for_message(self, recipient_name: str) -> str:
        """Return the governance scope for a message sent to the given recipient."""
        return self.recipient_scope_mapping.get(recipient_name, self.default_message_scope)

    def scope_for_tool(self, tool_name: str) -> str:
        """Return the governance scope for the given tool/function name."""
        return self.tool_scope_mapping.get(tool_name, self.default_tool_scope)
