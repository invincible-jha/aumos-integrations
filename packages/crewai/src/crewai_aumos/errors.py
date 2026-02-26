# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Integration-specific exceptions for crewai-aumos.

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
        subject: The name of the tool, task, or crew operation that was denied.
        agent_role: The role of the agent that triggered the evaluation.
        reason: Human-readable reason from the governance decision.
        decision: The raw governance decision object returned by the engine.
    """

    def __init__(
        self,
        subject: str,
        agent_role: str,
        reason: str,
        decision: Any,
    ) -> None:
        self.subject = subject
        self.agent_role = agent_role
        self.reason = reason
        self.decision = decision
        super().__init__(
            f"Governance denied '{subject}' for agent role '{agent_role}': {reason}"
        )


class TaskSkippedError(Exception):
    """
    Raised internally to signal that a task was skipped due to a denial when
    ``on_denied`` is set to ``'skip'``.

    This exception is caught by ``GovernedCrew.kickoff`` and converted into a
    benign skip message rather than propagated to the caller. It is exposed here
    so that custom crew implementations can handle it explicitly if needed.

    Attributes:
        task_description: Short description of the skipped task.
        agent_role: Role of the agent that was blocked from executing.
        reason: Human-readable reason from the governance decision.
    """

    def __init__(
        self,
        task_description: str,
        agent_role: str,
        reason: str,
    ) -> None:
        self.task_description = task_description
        self.agent_role = agent_role
        self.reason = reason
        super().__init__(
            f"Task skipped for agent role '{agent_role}' by governance: {reason}"
        )
