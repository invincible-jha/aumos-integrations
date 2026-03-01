# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Tests for autogen-aumos integration — GovernedConversableAgent, MessageGuard,
ToolGuard, AutoGenGovernanceConfig, and error types.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from autogen_aumos.config import AutoGenGovernanceConfig
from autogen_aumos.errors import GovernanceDeniedError, MessageBlockedError
from autogen_aumos.governed_agent import GovernedConversableAgent
from autogen_aumos.message_guard import MessageGuard
from autogen_aumos.tool_guard import ToolGuard
from autogen_aumos.types import (
    AuditRecord,
    DeniedAction,
    GuardResult,
    MessageContext,
    ToolCallContext,
)
from tests.conftest import _make_agent, _make_decision, _make_engine


# ---------------------------------------------------------------------------
# TestAutoGenGovernanceConfig
# ---------------------------------------------------------------------------


class TestAutoGenGovernanceConfig:
    def test_default_on_denied_is_raise(self) -> None:
        config = AutoGenGovernanceConfig()
        assert config.on_denied == DeniedAction.RAISE

    def test_default_message_scope(self) -> None:
        config = AutoGenGovernanceConfig()
        assert config.default_message_scope == "autogen_message"

    def test_default_tool_scope(self) -> None:
        config = AutoGenGovernanceConfig()
        assert config.default_tool_scope == "autogen_tool_call"

    def test_scope_for_message_returns_default_when_no_mapping(self) -> None:
        config = AutoGenGovernanceConfig()
        assert config.scope_for_message("executor") == "autogen_message"

    def test_scope_for_message_returns_mapped_scope(self) -> None:
        config = AutoGenGovernanceConfig(recipient_scope_mapping={"executor": "execution_scope"})
        assert config.scope_for_message("executor") == "execution_scope"

    def test_scope_for_tool_returns_default_when_no_mapping(self) -> None:
        config = AutoGenGovernanceConfig()
        assert config.scope_for_tool("run_code") == "autogen_tool_call"

    def test_scope_for_tool_returns_mapped_scope(self) -> None:
        config = AutoGenGovernanceConfig(tool_scope_mapping={"run_code": "code_execution"})
        assert config.scope_for_tool("run_code") == "code_execution"

    def test_coerces_string_on_denied_to_enum(self) -> None:
        config = AutoGenGovernanceConfig(on_denied="block")  # type: ignore[arg-type]
        assert config.on_denied == DeniedAction.BLOCK

    def test_config_is_frozen(self) -> None:
        config = AutoGenGovernanceConfig()
        with pytest.raises((AttributeError, TypeError)):
            config.on_denied = DeniedAction.LOG  # type: ignore[misc]

    def test_govern_messages_defaults_to_true(self) -> None:
        config = AutoGenGovernanceConfig()
        assert config.govern_messages is True

    def test_govern_tools_defaults_to_true(self) -> None:
        config = AutoGenGovernanceConfig()
        assert config.govern_tools is True


# ---------------------------------------------------------------------------
# TestMessageGuard
# ---------------------------------------------------------------------------


class TestMessageGuard:
    def test_returns_permitted_result_when_engine_allows(
        self, permitting_engine: MagicMock
    ) -> None:
        guard = MessageGuard(engine=permitting_engine)
        result = guard.check_message(
            sender_name="planner", recipient_name="executor", message="Do the task"
        )
        assert result.permitted is True
        assert result.agent_name == "planner"

    def test_calls_evaluate_sync_with_sender_as_agent_id(
        self, permitting_engine: MagicMock
    ) -> None:
        guard = MessageGuard(engine=permitting_engine)
        guard.check_message(
            sender_name="planner", recipient_name="executor", message="Hello"
        )
        call_kwargs = permitting_engine.evaluate_sync.call_args.kwargs
        assert call_kwargs.get("agent_id") == "planner"

    def test_scope_is_resolved_for_recipient(
        self, permitting_engine: MagicMock
    ) -> None:
        config = AutoGenGovernanceConfig(
            recipient_scope_mapping={"executor": "execution_scope"}
        )
        guard = MessageGuard(engine=permitting_engine, config=config)
        guard.check_message(
            sender_name="planner", recipient_name="executor", message="Execute"
        )
        call_kwargs = permitting_engine.evaluate_sync.call_args.kwargs
        assert call_kwargs.get("scope") == "execution_scope"

    def test_raises_governance_denied_error_on_denial_with_raise_mode(
        self, denying_engine: MagicMock, raise_config: AutoGenGovernanceConfig
    ) -> None:
        guard = MessageGuard(engine=denying_engine, config=raise_config)
        with pytest.raises(GovernanceDeniedError):
            guard.check_message(
                sender_name="planner", recipient_name="executor", message="Hi"
            )

    def test_raises_message_blocked_error_on_denial_with_block_mode(
        self, denying_engine: MagicMock, block_config: AutoGenGovernanceConfig
    ) -> None:
        guard = MessageGuard(engine=denying_engine, config=block_config)
        with pytest.raises(MessageBlockedError):
            guard.check_message(
                sender_name="planner", recipient_name="executor", message="Hi"
            )

    def test_returns_denied_result_on_denial_with_log_mode(
        self, denying_engine: MagicMock, log_config: AutoGenGovernanceConfig
    ) -> None:
        guard = MessageGuard(engine=denying_engine, config=log_config)
        result = guard.check_message(
            sender_name="planner", recipient_name="executor", message="Hi"
        )
        assert result.permitted is False

    def test_audit_event_recorded_when_audit_all_actions_true(
        self, permitting_engine: MagicMock
    ) -> None:
        config = AutoGenGovernanceConfig(audit_all_actions=True)
        guard = MessageGuard(engine=permitting_engine, config=config)
        guard.check_message(
            sender_name="planner", recipient_name="executor", message="Hello"
        )
        permitting_engine.record_audit_event.assert_called_once()

    def test_no_audit_event_when_audit_all_actions_false(
        self, permitting_engine: MagicMock
    ) -> None:
        config = AutoGenGovernanceConfig(audit_all_actions=False)
        guard = MessageGuard(engine=permitting_engine, config=config)
        guard.check_message(
            sender_name="planner", recipient_name="executor", message="Hello"
        )
        permitting_engine.record_audit_event.assert_not_called()


# ---------------------------------------------------------------------------
# TestToolGuard
# ---------------------------------------------------------------------------


class TestToolGuard:
    def test_returns_permitted_result_when_engine_allows(
        self, permitting_engine: MagicMock
    ) -> None:
        guard = ToolGuard(engine=permitting_engine)
        result = guard.check_tool(agent_name="executor", tool_name="run_code")
        assert result.permitted is True
        assert result.agent_name == "executor"

    def test_calls_evaluate_sync_with_agent_name_as_agent_id(
        self, permitting_engine: MagicMock
    ) -> None:
        guard = ToolGuard(engine=permitting_engine)
        guard.check_tool(agent_name="executor", tool_name="run_code")
        call_kwargs = permitting_engine.evaluate_sync.call_args.kwargs
        assert call_kwargs.get("agent_id") == "executor"

    def test_scope_is_resolved_from_config_for_tool(
        self, permitting_engine: MagicMock
    ) -> None:
        config = AutoGenGovernanceConfig(
            tool_scope_mapping={"run_code": "code_execution"}
        )
        guard = ToolGuard(engine=permitting_engine, config=config)
        guard.check_tool(agent_name="executor", tool_name="run_code")
        call_kwargs = permitting_engine.evaluate_sync.call_args.kwargs
        assert call_kwargs.get("scope") == "code_execution"

    def test_raises_governance_denied_error_on_denial_with_raise_mode(
        self, denying_engine: MagicMock, raise_config: AutoGenGovernanceConfig
    ) -> None:
        guard = ToolGuard(engine=denying_engine, config=raise_config)
        with pytest.raises(GovernanceDeniedError) as exc_info:
            guard.check_tool(agent_name="executor", tool_name="run_code")
        assert exc_info.value.subject == "run_code"
        assert exc_info.value.agent_name == "executor"

    def test_returns_denied_result_with_block_mode(
        self, denying_engine: MagicMock, block_config: AutoGenGovernanceConfig
    ) -> None:
        guard = ToolGuard(engine=denying_engine, config=block_config)
        result = guard.check_tool(agent_name="executor", tool_name="run_code")
        assert result.permitted is False

    def test_extracts_amount_field_from_args_when_configured(
        self, permitting_engine: MagicMock
    ) -> None:
        config = AutoGenGovernanceConfig(amount_field="cost")
        guard = ToolGuard(engine=permitting_engine, config=config)
        guard.check_tool(
            agent_name="executor", tool_name="api_call", args={"cost": 1.5}
        )
        call_kwargs = permitting_engine.evaluate_sync.call_args.kwargs
        assert call_kwargs.get("amount") == 1.5

    def test_amount_absent_when_field_not_in_args(
        self, permitting_engine: MagicMock
    ) -> None:
        config = AutoGenGovernanceConfig(amount_field="cost")
        guard = ToolGuard(engine=permitting_engine, config=config)
        guard.check_tool(
            agent_name="executor", tool_name="api_call", args={"query": "hello"}
        )
        call_kwargs = permitting_engine.evaluate_sync.call_args.kwargs
        assert "amount" not in call_kwargs

    def test_amount_not_passed_when_amount_field_not_configured(
        self, permitting_engine: MagicMock
    ) -> None:
        guard = ToolGuard(engine=permitting_engine)
        guard.check_tool(
            agent_name="executor", tool_name="api_call", args={"cost": 5.0}
        )
        call_kwargs = permitting_engine.evaluate_sync.call_args.kwargs
        assert "amount" not in call_kwargs

    def test_audit_event_recorded_when_permitted_and_audit_all_actions(
        self, permitting_engine: MagicMock
    ) -> None:
        config = AutoGenGovernanceConfig(audit_all_actions=True)
        guard = ToolGuard(engine=permitting_engine, config=config)
        guard.check_tool(agent_name="executor", tool_name="run_code")
        permitting_engine.record_audit_event.assert_called_once()


# ---------------------------------------------------------------------------
# TestGovernedConversableAgent
# ---------------------------------------------------------------------------


class TestGovernedConversableAgent:
    def test_trust_level_set_at_construction(
        self, permitting_engine: MagicMock
    ) -> None:
        agent = _make_agent("planner")
        GovernedConversableAgent(agent=agent, engine=permitting_engine, trust_level=3)
        permitting_engine.trust.set_level.assert_called_once()
        call_args = permitting_engine.trust.set_level.call_args
        # Second argument should be the trust level
        assert call_args[0][1] == 3

    def test_default_trust_level_is_2(self, permitting_engine: MagicMock) -> None:
        agent = _make_agent("planner")
        GovernedConversableAgent(agent=agent, engine=permitting_engine)
        call_args = permitting_engine.trust.set_level.call_args
        assert call_args[0][1] == 2

    def test_repr_contains_agent_name_and_trust_level(
        self, permitting_engine: MagicMock
    ) -> None:
        agent = _make_agent("planner")
        governed = GovernedConversableAgent(
            agent=agent, engine=permitting_engine, trust_level=5
        )
        repr_str = repr(governed)
        assert "planner" in repr_str
        assert "5" in repr_str

    def test_wrapped_agent_accessible_via_agent_property(
        self, permitting_engine: MagicMock
    ) -> None:
        agent = _make_agent("planner")
        governed = GovernedConversableAgent(agent=agent, engine=permitting_engine)
        assert governed.agent is agent

    def test_governance_message_hook_returns_message_when_permitted(
        self, permitting_engine: MagicMock
    ) -> None:
        agent = _make_agent("planner")
        governed = GovernedConversableAgent(agent=agent, engine=permitting_engine)
        sender = _make_agent("orchestrator")
        recipient = _make_agent("executor")
        result = governed.governance_message_hook(
            sender=sender,
            message="Do the task",
            recipient=recipient,
            silent=False,
        )
        assert result == "Do the task"

    def test_governance_message_hook_raises_on_denial_with_raise_mode(
        self, denying_engine: MagicMock
    ) -> None:
        agent = _make_agent("planner")
        config = AutoGenGovernanceConfig(on_denied=DeniedAction.RAISE)
        governed = GovernedConversableAgent(
            agent=agent, engine=denying_engine, config=config
        )
        sender = _make_agent("orchestrator")
        recipient = _make_agent("executor")
        with pytest.raises(GovernanceDeniedError):
            governed.governance_message_hook(
                sender=sender, message="Execute", recipient=recipient, silent=False
            )

    def test_governance_message_hook_returns_denial_notice_with_block_mode(
        self, denying_engine: MagicMock
    ) -> None:
        agent = _make_agent("planner")
        config = AutoGenGovernanceConfig(on_denied=DeniedAction.BLOCK)
        governed = GovernedConversableAgent(
            agent=agent, engine=denying_engine, config=config
        )
        sender = _make_agent("orchestrator")
        recipient = _make_agent("executor")
        result = governed.governance_message_hook(
            sender=sender, message="Execute", recipient=recipient, silent=False
        )
        assert isinstance(result, str)
        assert "governance" in result.lower() or "blocked" in result.lower()

    def test_governance_message_hook_passes_through_when_govern_messages_false(
        self, denying_engine: MagicMock
    ) -> None:
        agent = _make_agent("planner")
        config = AutoGenGovernanceConfig(
            on_denied=DeniedAction.RAISE, govern_messages=False
        )
        governed = GovernedConversableAgent(
            agent=agent, engine=denying_engine, config=config
        )
        sender = _make_agent("orchestrator")
        recipient = _make_agent("executor")
        # Should not raise even with denying engine when govern_messages=False
        result = governed.governance_message_hook(
            sender=sender, message="Pass through", recipient=recipient, silent=False
        )
        assert result == "Pass through"

    def test_governed_execute_function_returns_none_when_permitted(
        self, permitting_engine: MagicMock
    ) -> None:
        agent = _make_agent("executor")
        governed = GovernedConversableAgent(agent=agent, engine=permitting_engine)
        result = governed.governed_execute_function({"name": "run_code"})
        assert result is None

    def test_governed_execute_function_returns_error_dict_when_denied(
        self, denying_engine: MagicMock, block_config: AutoGenGovernanceConfig
    ) -> None:
        agent = _make_agent("executor")
        governed = GovernedConversableAgent(
            agent=agent, engine=denying_engine, config=block_config
        )
        result = governed.governed_execute_function({"name": "run_code"})
        assert result is not None
        assert "error" in result

    def test_governed_execute_function_raises_when_denied_and_raise_mode(
        self, denying_engine: MagicMock, raise_config: AutoGenGovernanceConfig
    ) -> None:
        agent = _make_agent("executor")
        governed = GovernedConversableAgent(
            agent=agent, engine=denying_engine, config=raise_config
        )
        with pytest.raises(GovernanceDeniedError):
            governed.governed_execute_function({"name": "run_code"})

    def test_governed_execute_function_skipped_when_govern_tools_false(
        self, denying_engine: MagicMock
    ) -> None:
        agent = _make_agent("executor")
        config = AutoGenGovernanceConfig(
            on_denied=DeniedAction.RAISE, govern_tools=False
        )
        governed = GovernedConversableAgent(
            agent=agent, engine=denying_engine, config=config
        )
        # Should not raise — governance is bypassed
        result = governed.governed_execute_function({"name": "run_code"})
        assert result is None

    def test_extract_func_args_parses_json_string_arguments(self) -> None:
        import json

        func_call = {"name": "api_call", "arguments": json.dumps({"param": "value"})}
        result = GovernedConversableAgent._extract_func_args(func_call)
        assert result == {"param": "value"}

    def test_extract_func_args_returns_dict_arguments_unchanged(self) -> None:
        func_call = {"name": "api_call", "arguments": {"param": "value"}}
        result = GovernedConversableAgent._extract_func_args(func_call)
        assert result == {"param": "value"}

    def test_extract_func_args_returns_empty_dict_for_missing_arguments(self) -> None:
        func_call = {"name": "api_call"}
        result = GovernedConversableAgent._extract_func_args(func_call)
        assert result == {}

    def test_extract_func_args_returns_empty_dict_for_invalid_json(self) -> None:
        func_call = {"name": "api_call", "arguments": "not valid json {{{"}
        result = GovernedConversableAgent._extract_func_args(func_call)
        assert result == {}


# ---------------------------------------------------------------------------
# TestGovernanceDeniedError
# ---------------------------------------------------------------------------


class TestGovernanceDeniedError:
    def test_stores_subject_agent_name_reason(self) -> None:
        decision = _make_decision(permitted=False)
        error = GovernanceDeniedError(
            subject="run_code",
            agent_name="executor",
            reason="policy blocked",
            decision=decision,
        )
        assert error.subject == "run_code"
        assert error.agent_name == "executor"
        assert error.reason == "policy blocked"

    def test_is_instance_of_exception(self) -> None:
        error = GovernanceDeniedError(
            subject="tool", agent_name="agent", reason="denied", decision=None
        )
        assert isinstance(error, Exception)

    def test_message_contains_subject_and_agent(self) -> None:
        error = GovernanceDeniedError(
            subject="my_tool", agent_name="my_agent", reason="blocked", decision=None
        )
        assert "my_tool" in str(error)
        assert "my_agent" in str(error)


# ---------------------------------------------------------------------------
# TestMessageBlockedError
# ---------------------------------------------------------------------------


class TestMessageBlockedError:
    def test_stores_sender_recipient_reason(self) -> None:
        error = MessageBlockedError(
            sender_name="planner",
            recipient_name="executor",
            reason="communication blocked",
        )
        assert error.sender_name == "planner"
        assert error.recipient_name == "executor"
        assert error.reason == "communication blocked"

    def test_is_instance_of_exception(self) -> None:
        error = MessageBlockedError(
            sender_name="a", recipient_name="b", reason="blocked"
        )
        assert isinstance(error, Exception)


# ---------------------------------------------------------------------------
# TestAutoGenTypes
# ---------------------------------------------------------------------------


class TestAutoGenTypes:
    def test_message_context_is_pydantic_model(self) -> None:
        ctx = MessageContext(
            sender_name="planner",
            recipient_name="executor",
            message_preview="Hello",
            scope="autogen_message",
        )
        assert ctx.sender_name == "planner"
        assert ctx.extra == {}

    def test_tool_call_context_defaults_amount_to_none(self) -> None:
        ctx = ToolCallContext(
            agent_name="executor",
            tool_name="run_code",
            scope="autogen_tool_call",
        )
        assert ctx.amount is None

    def test_guard_result_defaults_reason_to_empty_string(self) -> None:
        result = GuardResult(permitted=True, scope="autogen_message", agent_name="planner")
        assert result.reason == ""

    def test_audit_record_defaults_error_and_preview_to_none(self) -> None:
        record = AuditRecord(subject="message", agent_name="planner", succeeded=True)
        assert record.error_message is None
        assert record.output_preview is None

    def test_denied_action_enum_values(self) -> None:
        assert DeniedAction.RAISE == "raise"
        assert DeniedAction.BLOCK == "block"
        assert DeniedAction.LOG == "log"
