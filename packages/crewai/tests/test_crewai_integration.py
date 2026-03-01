# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Tests for crewai-aumos integration — GovernedCrewTool, wrap_tools,
CrewGovernanceConfig, and error types.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, call

import pytest

from crewai_aumos.config import CrewGovernanceConfig
from crewai_aumos.errors import GovernanceDeniedError, TaskSkippedError
from crewai_aumos.governed_agent import GovernedCrewTool, wrap_tools
from crewai_aumos.types import (
    AuditRecord,
    DeniedAction,
    GuardResult,
    TaskContext,
    ToolCallContext,
)
from tests.conftest import _make_decision, _make_engine, _make_tool


# ---------------------------------------------------------------------------
# TestCrewGovernanceConfig
# ---------------------------------------------------------------------------


class TestCrewGovernanceConfig:
    def test_default_on_denied_is_raise(self) -> None:
        config = CrewGovernanceConfig()
        assert config.on_denied == DeniedAction.RAISE

    def test_default_tool_scope(self) -> None:
        config = CrewGovernanceConfig()
        assert config.default_tool_scope == "crew_tool_call"

    def test_default_task_scope(self) -> None:
        config = CrewGovernanceConfig()
        assert config.default_task_scope == "crew_task"

    def test_scope_for_tool_returns_default_when_no_mapping(self) -> None:
        config = CrewGovernanceConfig()
        assert config.scope_for_tool("my_tool") == "crew_tool_call"

    def test_scope_for_tool_returns_mapped_scope(self) -> None:
        config = CrewGovernanceConfig(tool_scope_mapping={"search": "web_search"})
        assert config.scope_for_tool("search") == "web_search"

    def test_scope_for_task_returns_default_when_no_mapping(self) -> None:
        config = CrewGovernanceConfig()
        assert config.scope_for_task("analyst") == "crew_task"

    def test_scope_for_task_returns_mapped_scope(self) -> None:
        config = CrewGovernanceConfig(agent_task_scope_mapping={"analyst": "analysis_task"})
        assert config.scope_for_task("analyst") == "analysis_task"

    def test_coerces_string_on_denied_to_enum(self) -> None:
        config = CrewGovernanceConfig(on_denied="skip")  # type: ignore[arg-type]
        assert config.on_denied == DeniedAction.SKIP

    def test_config_is_frozen(self) -> None:
        config = CrewGovernanceConfig()
        with pytest.raises((AttributeError, TypeError)):
            config.on_denied = DeniedAction.LOG  # type: ignore[misc]

    def test_audit_output_preview_length_default_is_256(self) -> None:
        config = CrewGovernanceConfig()
        assert config.audit_output_preview_length == 256


# ---------------------------------------------------------------------------
# TestGovernedCrewTool — name and description delegation
# ---------------------------------------------------------------------------


class TestGovernedCrewToolProperties:
    def test_name_delegates_to_inner_tool(
        self, permitting_engine: MagicMock
    ) -> None:
        tool = _make_tool("calculator")
        governed = GovernedCrewTool(tool=tool, engine=permitting_engine, agent_role="analyst")
        assert governed.name == "calculator"

    def test_description_delegates_to_inner_tool(
        self, permitting_engine: MagicMock
    ) -> None:
        tool = _make_tool("calculator")
        governed = GovernedCrewTool(tool=tool, engine=permitting_engine, agent_role="analyst")
        assert "calculator" in governed.description

    def test_repr_contains_tool_name_and_agent_role(
        self, permitting_engine: MagicMock
    ) -> None:
        tool = _make_tool("search")
        governed = GovernedCrewTool(tool=tool, engine=permitting_engine, agent_role="researcher")
        repr_str = repr(governed)
        assert "search" in repr_str
        assert "researcher" in repr_str


# ---------------------------------------------------------------------------
# TestGovernedCrewTool — permitted execution
# ---------------------------------------------------------------------------


class TestGovernedCrewToolPermitted:
    def test_delegates_to_inner_tool_run_when_permitted(
        self, permitting_engine: MagicMock
    ) -> None:
        tool = _make_tool("search", output="search results")
        governed = GovernedCrewTool(tool=tool, engine=permitting_engine, agent_role="analyst")
        result = governed.run("query string")
        assert result == "search results"
        tool.run.assert_called_once()

    def test_run_calls_evaluate_sync_with_agent_id(
        self, permitting_engine: MagicMock
    ) -> None:
        tool = _make_tool("search")
        governed = GovernedCrewTool(tool=tool, engine=permitting_engine, agent_role="researcher")
        governed.run("a query")
        call_kwargs = permitting_engine.evaluate_sync.call_args.kwargs
        assert call_kwargs.get("agent_id") == "researcher"

    def test_run_passes_scope_to_engine(
        self, permitting_engine: MagicMock
    ) -> None:
        tool = _make_tool("search")
        config = CrewGovernanceConfig(tool_scope_mapping={"search": "web_search_scope"})
        governed = GovernedCrewTool(
            tool=tool, engine=permitting_engine, agent_role="analyst", config=config
        )
        governed.run("query")
        call_kwargs = permitting_engine.evaluate_sync.call_args.kwargs
        assert call_kwargs.get("scope") == "web_search_scope"

    def test_run_includes_budget_category_when_set(
        self, permitting_engine: MagicMock
    ) -> None:
        tool = _make_tool("search")
        governed = GovernedCrewTool(
            tool=tool,
            engine=permitting_engine,
            agent_role="analyst",
            budget_category="web_searches",
        )
        governed.run("query")
        call_kwargs = permitting_engine.evaluate_sync.call_args.kwargs
        assert call_kwargs.get("budget_category") == "web_searches"

    def test_run_includes_required_trust_level_when_nonzero(
        self, permitting_engine: MagicMock
    ) -> None:
        tool = _make_tool("admin_tool")
        governed = GovernedCrewTool(
            tool=tool,
            engine=permitting_engine,
            agent_role="admin",
            required_trust_level=2,
        )
        governed.run()
        call_kwargs = permitting_engine.evaluate_sync.call_args.kwargs
        assert call_kwargs.get("required_trust_level") == 2

    def test_run_proxied_via_underscore_run(
        self, permitting_engine: MagicMock
    ) -> None:
        tool = _make_tool("search", output="result via _run")
        governed = GovernedCrewTool(tool=tool, engine=permitting_engine, agent_role="analyst")
        result = governed._run("query")
        assert result == "result via _run"

    def test_inner_tool_with_only_underscore_run_is_called(
        self, permitting_engine: MagicMock
    ) -> None:
        tool = MagicMock()
        tool.name = "legacy_tool"
        tool.description = "Legacy"
        # Only _run exists, not run
        del tool.run
        tool._run.return_value = "legacy output"
        governed = GovernedCrewTool(tool=tool, engine=permitting_engine, agent_role="analyst")
        result = governed.run("input")
        assert result == "legacy output"

    def test_tool_without_run_or_underscore_run_raises_type_error(
        self, permitting_engine: MagicMock
    ) -> None:
        tool = MagicMock(spec=[])
        tool.name = "broken_tool"
        governed = GovernedCrewTool(tool=tool, engine=permitting_engine, agent_role="analyst")
        with pytest.raises(TypeError, match="does not expose a callable"):
            governed.run("input")


# ---------------------------------------------------------------------------
# TestGovernedCrewTool — denial handling
# ---------------------------------------------------------------------------


class TestGovernedCrewToolDenials:
    def test_on_denied_raise_raises_governance_denied_error(
        self, denying_engine: MagicMock, default_config: CrewGovernanceConfig
    ) -> None:
        tool = _make_tool("search")
        governed = GovernedCrewTool(
            tool=tool, engine=denying_engine, agent_role="analyst", config=default_config
        )
        with pytest.raises(GovernanceDeniedError) as exc_info:
            governed.run("query")
        assert exc_info.value.subject == "search"
        assert exc_info.value.agent_role == "analyst"

    def test_on_denied_skip_returns_denial_message_string(
        self, denying_engine: MagicMock, skip_config: CrewGovernanceConfig
    ) -> None:
        tool = _make_tool("search")
        governed = GovernedCrewTool(
            tool=tool, engine=denying_engine, agent_role="analyst", config=skip_config
        )
        result = governed.run("query")
        assert "governance" in result.lower() or "skip" in result.lower() or "denied" in result.lower()
        # Inner tool must NOT be called
        tool.run.assert_not_called()

    def test_on_denied_log_returns_empty_string(
        self, denying_engine: MagicMock, log_config: CrewGovernanceConfig
    ) -> None:
        tool = _make_tool("search")
        governed = GovernedCrewTool(
            tool=tool, engine=denying_engine, agent_role="analyst", config=log_config
        )
        result = governed.run("query")
        assert result == ""
        tool.run.assert_not_called()

    def test_denial_does_not_invoke_inner_tool(
        self, denying_engine: MagicMock, skip_config: CrewGovernanceConfig
    ) -> None:
        tool = _make_tool("search")
        governed = GovernedCrewTool(
            tool=tool, engine=denying_engine, agent_role="analyst", config=skip_config
        )
        governed.run("query")
        tool.run.assert_not_called()
        tool._run.assert_not_called()


# ---------------------------------------------------------------------------
# TestGovernedCrewTool — audit behaviour
# ---------------------------------------------------------------------------


class TestGovernedCrewToolAudit:
    def test_record_audit_event_called_on_success_when_audit_all_calls(
        self, permitting_engine: MagicMock
    ) -> None:
        tool = _make_tool("search", output="result")
        config = CrewGovernanceConfig(audit_all_calls=True)
        governed = GovernedCrewTool(
            tool=tool, engine=permitting_engine, agent_role="analyst", config=config
        )
        governed.run("query")
        permitting_engine.record_audit_event.assert_called_once()

    def test_no_audit_event_when_audit_all_calls_is_false(
        self, permitting_engine: MagicMock
    ) -> None:
        tool = _make_tool("search", output="result")
        config = CrewGovernanceConfig(audit_all_calls=False)
        governed = GovernedCrewTool(
            tool=tool, engine=permitting_engine, agent_role="analyst", config=config
        )
        governed.run("query")
        permitting_engine.record_audit_event.assert_not_called()

    def test_audit_preview_is_truncated_to_config_length(
        self, permitting_engine: MagicMock
    ) -> None:
        long_output = "x" * 500
        tool = _make_tool("search", output=long_output)
        config = CrewGovernanceConfig(audit_output_preview_length=10, audit_all_calls=True)
        governed = GovernedCrewTool(
            tool=tool, engine=permitting_engine, agent_role="analyst", config=config
        )
        governed.run("query")
        call_kwargs = permitting_engine.record_audit_event.call_args.kwargs
        preview = call_kwargs.get("output_preview")
        assert preview is not None
        assert len(preview) == 10

    def test_audit_preview_is_none_when_preview_length_zero(
        self, permitting_engine: MagicMock
    ) -> None:
        tool = _make_tool("search", output="result")
        config = CrewGovernanceConfig(audit_output_preview_length=0, audit_all_calls=True)
        governed = GovernedCrewTool(
            tool=tool, engine=permitting_engine, agent_role="analyst", config=config
        )
        governed.run("query")
        call_kwargs = permitting_engine.record_audit_event.call_args.kwargs
        assert call_kwargs.get("output_preview") is None


# ---------------------------------------------------------------------------
# TestWrapTools
# ---------------------------------------------------------------------------


class TestWrapTools:
    def test_returns_a_governed_tool_for_each_input_tool(
        self, permitting_engine: MagicMock
    ) -> None:
        tools = [_make_tool("search"), _make_tool("calculator")]
        governed = wrap_tools(tools, permitting_engine, agent_role="analyst")
        assert len(governed) == 2
        assert all(isinstance(t, GovernedCrewTool) for t in governed)

    def test_preserves_tool_order(self, permitting_engine: MagicMock) -> None:
        tools = [_make_tool("search"), _make_tool("calculator"), _make_tool("email")]
        governed = wrap_tools(tools, permitting_engine, agent_role="analyst")
        assert governed[0].name == "search"
        assert governed[1].name == "calculator"
        assert governed[2].name == "email"

    def test_wraps_empty_list_without_error(self, permitting_engine: MagicMock) -> None:
        governed = wrap_tools([], permitting_engine, agent_role="analyst")
        assert governed == []

    def test_agent_role_is_applied_to_all_wrapped_tools(
        self, permitting_engine: MagicMock
    ) -> None:
        tools = [_make_tool("search"), _make_tool("calculator")]
        governed = wrap_tools(tools, permitting_engine, agent_role="specialist")
        for t in governed:
            repr_str = repr(t)
            assert "specialist" in repr_str


# ---------------------------------------------------------------------------
# TestGovernanceDeniedError
# ---------------------------------------------------------------------------


class TestGovernanceDeniedError:
    def test_stores_subject_agent_role_reason(self) -> None:
        decision = _make_decision(permitted=False)
        error = GovernanceDeniedError(
            subject="search_tool",
            agent_role="analyst",
            reason="policy blocked",
            decision=decision,
        )
        assert error.subject == "search_tool"
        assert error.agent_role == "analyst"
        assert error.reason == "policy blocked"

    def test_is_instance_of_exception(self) -> None:
        error = GovernanceDeniedError(
            subject="tool", agent_role="role", reason="denied", decision=None
        )
        assert isinstance(error, Exception)

    def test_string_representation_contains_subject_and_role(self) -> None:
        error = GovernanceDeniedError(
            subject="my_tool", agent_role="my_role", reason="blocked", decision=None
        )
        assert "my_tool" in str(error)
        assert "my_role" in str(error)


# ---------------------------------------------------------------------------
# TestTypes
# ---------------------------------------------------------------------------


class TestCrewAITypes:
    def test_tool_call_context_is_pydantic_model(self) -> None:
        ctx = ToolCallContext(
            tool_name="search",
            agent_role="analyst",
            scope="crew_tool_call",
            serialized_input="query",
        )
        assert ctx.tool_name == "search"
        assert ctx.amount is None

    def test_task_context_defaults_tools_to_empty_list(self) -> None:
        ctx = TaskContext(
            task_description="Analyze data",
            agent_role="analyst",
            scope="crew_task",
        )
        assert ctx.tools == []

    def test_guard_result_permitted_field(self) -> None:
        result = GuardResult(permitted=True, scope="crew_task", agent_role="analyst")
        assert result.permitted is True
        assert result.reason == ""

    def test_audit_record_defaults_error_message_to_none(self) -> None:
        record = AuditRecord(tool_name="search", agent_role="analyst", succeeded=True)
        assert record.error_message is None

    def test_denied_action_enum_values(self) -> None:
        assert DeniedAction.RAISE == "raise"
        assert DeniedAction.SKIP == "skip"
        assert DeniedAction.LOG == "log"
