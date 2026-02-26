# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
crewai-aumos — AumOS governance integration for CrewAI multi-agent crews.

Add AumOS governance to any CrewAI crew in a few lines:

.. code-block:: python

    from crewai import Crew, Agent, Task
    from crewai_aumos import GovernedCrew

    engine = GovernanceEngine(config)
    governed = GovernedCrew(crew=crew, engine=engine)
    result = governed.kickoff(inputs={"topic": "AI safety"})

Every tool call each agent makes is evaluated against your governance policy
before execution. Denied calls raise ``GovernanceDeniedError``, skip with a
message, or are logged — your choice.

Public API
----------
GovernedCrew
    Wraps a CrewAI ``Crew`` with per-agent governance. Replaces each agent's
    tools with governed wrappers and evaluates task-level checkpoints before
    ``kickoff``.

GovernedCrewTool
    Wraps a single CrewAI tool with a governance gate. Used directly when you
    need per-tool trust level requirements or budget categories.

wrap_tools
    Convenience function to wrap a list of tools for a given agent role.

TaskGuard
    Governance guard for task-level checkpoints. Evaluates governance before
    an agent is dispatched to execute a task.

CrewGovernanceConfig
    Pydantic v2 configuration model for the integration.

GovernanceDeniedError
    Raised when governance denies an action and ``on_denied='raise'``.

TaskSkippedError
    Internal signal that a task was skipped; exposed for custom implementations.

DeniedAction
    Enum of denial handling modes: ``RAISE``, ``SKIP``, ``LOG``.

GuardResult
    Outcome of a governance guard check. Returned by ``TaskGuard.guard_task``.
"""

from .config import CrewGovernanceConfig
from .errors import GovernanceDeniedError, TaskSkippedError
from .governed_agent import GovernedCrewTool, wrap_tools
from .governed_crew import GovernedCrew
from .task_guard import TaskGuard
from .types import AuditRecord, DeniedAction, GuardResult, TaskContext, ToolCallContext

__all__ = [
    "GovernedCrew",
    "GovernedCrewTool",
    "wrap_tools",
    "TaskGuard",
    "CrewGovernanceConfig",
    "GovernanceDeniedError",
    "TaskSkippedError",
    "DeniedAction",
    "GuardResult",
    "AuditRecord",
    "TaskContext",
    "ToolCallContext",
]

__version__ = "0.1.0"
