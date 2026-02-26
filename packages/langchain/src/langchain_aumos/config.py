# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Configuration for langchain-aumos integration.

All runtime behaviour of the integration is controlled through ``GovernanceConfig``.
Values are validated at construction time via Pydantic v2 — errors surface before
any agent run begins.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field, model_validator

from .types import DeniedAction


class GovernanceConfig(BaseModel):
    """
    Configuration for the AumOS governance integration with LangChain.

    Pass an instance of this to ``AumOSGovernanceCallback``, ``GovernedTool``, or
    ``ChainGuard`` to control how governance decisions affect agent behaviour.

    Attributes:
        agent_id: Identifier for the agent being governed. Used in all evaluation
            requests and audit records.
        on_denied: What to do when a governance evaluation returns a denial.
            ``'raise'`` — raise ``GovernanceDeniedError`` (default).
            ``'skip'`` — return the denial message as the tool output; agent continues.
            ``'log'`` — log the denial and allow execution to proceed.
        default_scope: Governance scope sent for tool calls whose name does not
            appear in ``scope_mapping``. Defaults to ``'tool_call'``.
        scope_mapping: Optional mapping from tool name to governance scope string.
            If a tool name is present here, its mapped scope is used instead of
            ``default_scope``.
        amount_field: If set, the integration will attempt to parse this field
            name from the JSON-decoded tool input and pass it as the spend amount
            to the governance evaluation. If the field is absent or the input is
            not JSON, the amount is omitted.
        audit_all_calls: When True, record an audit event for every completed tool
            call (both allowed and denied). When False, only denied calls are
            audited. Defaults to True.
        audit_output_preview_length: Maximum number of characters of tool output
            to include in the audit record. Set to 0 to omit output previews.
            Defaults to 256.
    """

    agent_id: str = Field(
        default="default",
        min_length=1,
        description="Identifier for the agent being governed.",
    )
    on_denied: DeniedAction = Field(
        default=DeniedAction.RAISE,
        description="Action to take when governance denies a tool call.",
    )
    default_scope: str = Field(
        default="tool_call",
        min_length=1,
        description="Governance scope used when no scope_mapping entry exists for a tool.",
    )
    scope_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Optional per-tool governance scope overrides.",
    )
    amount_field: str | None = Field(
        default=None,
        description=(
            "JSON field name to extract as the spend amount from tool inputs. "
            "Omit if the tools do not carry spend amounts."
        ),
    )
    audit_all_calls: bool = Field(
        default=True,
        description="Record an audit event for every completed tool call.",
    )
    audit_output_preview_length: Annotated[int, Field(ge=0, le=4096)] = Field(
        default=256,
        description="Maximum characters of tool output included in audit records.",
    )

    model_config = {"frozen": True}

    @model_validator(mode="before")
    @classmethod
    def coerce_on_denied(cls, values: Any) -> Any:
        """Accept plain strings for on_denied in addition to the enum."""
        if isinstance(values, dict) and isinstance(values.get("on_denied"), str):
            values["on_denied"] = DeniedAction(values["on_denied"])
        return values

    def scope_for_tool(self, tool_name: str) -> str:
        """Return the governance scope for the given tool name."""
        return self.scope_mapping.get(tool_name, self.default_scope)
