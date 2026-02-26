# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Integration-specific exceptions for langchain-aumos.

These exceptions surface governance decisions as standard Python exceptions so
that callers can catch and handle them without importing from aumos-governance
directly.
"""

from __future__ import annotations

from typing import Any


class GovernanceDeniedError(Exception):
    """
    Raised when a governance evaluation returns a denial and ``on_denied`` is set
    to ``'raise'``.

    Attributes:
        tool_name: The name of the LangChain tool whose execution was denied.
        agent_id: The agent identifier that triggered the evaluation.
        reason: Human-readable reason from the governance decision.
        decision: The raw governance decision object returned by the engine.
    """

    def __init__(
        self,
        tool_name: str,
        agent_id: str,
        reason: str,
        decision: Any,
    ) -> None:
        self.tool_name = tool_name
        self.agent_id = agent_id
        self.reason = reason
        self.decision = decision
        super().__init__(
            f"Governance denied tool '{tool_name}' for agent '{agent_id}': {reason}"
        )


class ToolSkippedError(Exception):
    """
    Raised internally to signal that a tool call was skipped due to a denial when
    ``on_denied`` is set to ``'skip'``.

    This exception is caught by the callback and converted into a benign skip
    rather than propagated to the caller. It is exposed here so that subclasses
    and custom callback implementations can handle it explicitly if needed.

    Attributes:
        tool_name: The name of the skipped tool.
        reason: Human-readable reason from the governance decision.
    """

    def __init__(self, tool_name: str, reason: str) -> None:
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(
            f"Tool '{tool_name}' skipped by governance: {reason}"
        )
