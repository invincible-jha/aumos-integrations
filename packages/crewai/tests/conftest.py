# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""Shared fixtures for crewai-aumos integration tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from crewai_aumos.config import CrewGovernanceConfig
from crewai_aumos.types import DeniedAction


def _make_decision(permitted: bool, reason: str = "policy reason") -> MagicMock:
    """Build a mock governance decision object."""
    decision = MagicMock()
    decision.allowed = permitted
    decision.reason = reason
    return decision


def _make_engine(permitted: bool = True, reason: str = "") -> MagicMock:
    """Build a mock governance engine that returns a fixed decision."""
    engine = MagicMock()
    engine.evaluate_sync.return_value = _make_decision(permitted=permitted, reason=reason)
    engine.record_audit_event = MagicMock()
    return engine


def _make_tool(name: str = "search", output: str = "tool output") -> MagicMock:
    """Build a minimal mock CrewAI tool."""
    tool = MagicMock()
    tool.name = name
    tool.description = f"A mock {name} tool"
    tool.run.return_value = output
    return tool


@pytest.fixture
def permitting_engine() -> MagicMock:
    """A governance engine that always permits."""
    return _make_engine(permitted=True)


@pytest.fixture
def denying_engine() -> MagicMock:
    """A governance engine that always denies."""
    return _make_engine(permitted=False, reason="policy denied")


@pytest.fixture
def default_config() -> CrewGovernanceConfig:
    """Default CrewGovernanceConfig (on_denied=RAISE)."""
    return CrewGovernanceConfig()


@pytest.fixture
def skip_config() -> CrewGovernanceConfig:
    """Config with on_denied=SKIP."""
    return CrewGovernanceConfig(on_denied=DeniedAction.SKIP)


@pytest.fixture
def log_config() -> CrewGovernanceConfig:
    """Config with on_denied=LOG."""
    return CrewGovernanceConfig(on_denied=DeniedAction.LOG)
