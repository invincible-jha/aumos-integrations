# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Tests for langchain-aumos integration — GovernanceConfig, types, and callback logic.

These tests mock the LangChain and aumos-governance dependencies so they run
without requiring those packages to be installed.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from langchain_aumos.config import GovernanceConfig
from langchain_aumos.types import AuditRecord, DeniedAction, ToolCallContext


# ── GovernanceConfig validation ───────────────────────────────────────────────


class TestGovernanceConfig:
    def test_default_values_are_applied(self) -> None:
        config = GovernanceConfig()
        assert config.agent_id == "default"
        assert config.on_denied == DeniedAction.RAISE
        assert config.default_scope == "tool_call"
        assert config.audit_all_calls is True

    def test_custom_agent_id_is_accepted(self) -> None:
        config = GovernanceConfig(agent_id="my-agent-001")
        assert config.agent_id == "my-agent-001"

    def test_empty_agent_id_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            GovernanceConfig(agent_id="")

    def test_on_denied_accepts_raise_skip_log(self) -> None:
        for action in (DeniedAction.RAISE, DeniedAction.SKIP, DeniedAction.LOG):
            config = GovernanceConfig(on_denied=action)
            assert config.on_denied == action

    def test_on_denied_accepts_string_values(self) -> None:
        config = GovernanceConfig(on_denied="skip")
        assert config.on_denied == DeniedAction.SKIP

    def test_scope_mapping_is_optional(self) -> None:
        config = GovernanceConfig(
            scope_mapping={"send-email": "email_tool", "read-file": "file_tool"}
        )
        assert config.scope_mapping["send-email"] == "email_tool"

    def test_audit_output_preview_length_defaults_to_256(self) -> None:
        config = GovernanceConfig()
        assert config.audit_output_preview_length == 256


# ── ToolCallContext ────────────────────────────────────────────────────────────


class TestToolCallContext:
    def test_valid_context_construction(self) -> None:
        context = ToolCallContext(
            tool_name="read-email",
            agent_id="agent-001",
            scope="email_tool",
            input_str='{"to": "user@example.com"}',
        )
        assert context.tool_name == "read-email"
        assert context.agent_id == "agent-001"
        assert context.scope == "email_tool"

    def test_amount_is_optional(self) -> None:
        context = ToolCallContext(
            tool_name="read-data",
            agent_id="agent-001",
            scope="data_tool",
            input_str="query",
        )
        assert context.amount is None

    def test_amount_can_be_set(self) -> None:
        context = ToolCallContext(
            tool_name="api-call",
            agent_id="agent-001",
            scope="api_tool",
            input_str="{}",
            amount=2.5,
        )
        assert context.amount == 2.5

    def test_extra_metadata_defaults_to_empty_dict(self) -> None:
        context = ToolCallContext(
            tool_name="tool",
            agent_id="agent",
            scope="scope",
            input_str="input",
        )
        assert context.extra == {}


# ── AuditRecord ────────────────────────────────────────────────────────────────


class TestAuditRecord:
    def test_successful_audit_record(self) -> None:
        record = AuditRecord(
            tool_name="read-data",
            agent_id="agent-001",
            succeeded=True,
        )
        assert record.succeeded is True
        assert record.error_message is None

    def test_failed_audit_record_carries_error_message(self) -> None:
        record = AuditRecord(
            tool_name="delete-file",
            agent_id="agent-001",
            succeeded=False,
            error_message="Permission denied",
        )
        assert record.succeeded is False
        assert record.error_message == "Permission denied"

    def test_output_preview_is_optional(self) -> None:
        record = AuditRecord(
            tool_name="tool",
            agent_id="agent",
            succeeded=True,
        )
        assert record.output_preview is None


# ── DeniedAction enum ─────────────────────────────────────────────────────────


class TestDeniedAction:
    def test_enum_values_are_strings(self) -> None:
        assert DeniedAction.RAISE == "raise"
        assert DeniedAction.SKIP == "skip"
        assert DeniedAction.LOG == "log"

    def test_all_three_actions_exist(self) -> None:
        actions = list(DeniedAction)
        assert len(actions) == 3


# ── AumOSGovernanceCallback (mocked) ─────────────────────────────────────────


class TestAumOSGovernanceCallbackConstructor:
    def test_callback_stores_config_from_explicit_config_argument(self) -> None:
        """When a GovernanceConfig is provided, the callback uses it."""
        from langchain_aumos.callback import AumOSGovernanceCallback

        mock_engine = MagicMock()
        config = GovernanceConfig(agent_id="explicit-agent", on_denied=DeniedAction.LOG)
        callback = AumOSGovernanceCallback(mock_engine, config=config)
        assert callback._config.agent_id == "explicit-agent"
        assert callback._config.on_denied == DeniedAction.LOG

    def test_callback_builds_default_config_from_agent_id_param(self) -> None:
        from langchain_aumos.callback import AumOSGovernanceCallback

        mock_engine = MagicMock()
        callback = AumOSGovernanceCallback(mock_engine, agent_id="positional-agent")
        assert callback._config.agent_id == "positional-agent"
