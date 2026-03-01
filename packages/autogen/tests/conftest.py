# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""Shared fixtures for autogen-aumos integration tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from autogen_aumos.config import AutoGenGovernanceConfig
from autogen_aumos.types import DeniedAction


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
    engine.trust = MagicMock()
    engine.trust.set_level = MagicMock()
    return engine


def _make_agent(name: str = "planner") -> MagicMock:
    """Build a minimal mock AutoGen ConversableAgent."""
    agent = MagicMock()
    agent.name = name
    agent.register_reply = MagicMock()
    return agent


@pytest.fixture
def permitting_engine() -> MagicMock:
    """A governance engine that always permits."""
    return _make_engine(permitted=True)


@pytest.fixture
def denying_engine() -> MagicMock:
    """A governance engine that always denies."""
    return _make_engine(permitted=False, reason="policy denied")


@pytest.fixture
def raise_config() -> AutoGenGovernanceConfig:
    """Config with on_denied=RAISE (default)."""
    return AutoGenGovernanceConfig()


@pytest.fixture
def block_config() -> AutoGenGovernanceConfig:
    """Config with on_denied=BLOCK."""
    return AutoGenGovernanceConfig(on_denied=DeniedAction.BLOCK)


@pytest.fixture
def log_config() -> AutoGenGovernanceConfig:
    """Config with on_denied=LOG."""
    return AutoGenGovernanceConfig(on_denied=DeniedAction.LOG)
