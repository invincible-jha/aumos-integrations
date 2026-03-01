# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Integration-specific exceptions for adk-aumos.

These exceptions surface governance decisions as standard Python exceptions so
that callers can catch and handle them without importing from aumos-governance
directly.
"""

from __future__ import annotations


class GovernanceDeniedError(Exception):
    """
    Raised when a governance evaluation returns a denial and ``on_denied`` is
    set to ``'raise'``.

    Attributes:
        tool_name: The name of the ADK tool whose execution was denied.
        agent_id: The ADK agent identifier that triggered the evaluation.
        reason: Human-readable reason from the governance decision.
    """

    def __init__(
        self,
        tool_name: str,
        agent_id: str,
        reason: str,
    ) -> None:
        self.tool_name = tool_name
        self.agent_id = agent_id
        self.reason = reason
        super().__init__(
            f"Governance denied ADK tool '{tool_name}' for agent '{agent_id}': {reason}"
        )
