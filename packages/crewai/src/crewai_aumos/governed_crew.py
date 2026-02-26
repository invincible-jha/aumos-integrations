# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
GovernedCrew — wraps a CrewAI Crew with per-agent governance.

``GovernedCrew`` is the top-level entry point for the crewai-aumos integration.
It accepts an existing ``Crew`` object and an ``aumos-governance`` engine, and
produces a governed crew whose every tool call and task dispatch is evaluated
against the configured governance policy before execution is permitted.

The wrapper uses composition throughout: the original ``Crew`` object is never
subclassed. Governance is applied by replacing each agent's tool list with
``GovernedCrewTool`` instances before ``Crew.kickoff`` is called.

Trust levels are set manually by the operator via ``agent_trust_levels``. They
are never computed from runtime behaviour.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .config import CrewGovernanceConfig
from .errors import GovernanceDeniedError, TaskSkippedError
from .governed_agent import GovernedCrewTool
from .task_guard import TaskGuard
from .types import DeniedAction

logger = logging.getLogger(__name__)


class GovernedCrew:
    """
    Wrap a CrewAI ``Crew`` with per-agent governance.

    On construction, each agent in the crew has its tools replaced with
    ``GovernedCrewTool`` wrappers. When ``kickoff`` is called, the governed
    crew also evaluates a ``TaskGuard`` checkpoint before each task is
    dispatched to its assigned agent.

    Args:
        crew: The CrewAI ``Crew`` instance to govern.
        engine: An initialized ``aumos-governance`` ``GovernanceEngine`` instance.
        config: Optional ``CrewGovernanceConfig`` controlling denial handling,
            scope mapping, and audit behaviour. Defaults are used when omitted.
        agent_trust_levels: Optional mapping from agent role string to trust level
            integer. Trust levels are set manually by the operator at
            initialization time — they are never modified at runtime.
            If an agent role is not in this mapping, trust level ``0`` is used.

    Example::

        from crewai import Crew, Agent, Task
        from crewai_aumos import GovernedCrew

        crew = Crew(agents=[researcher, writer], tasks=[research_task, write_task])
        governed = GovernedCrew(crew=crew, engine=engine)
        result = governed.kickoff(inputs={"topic": "AI safety"})
    """

    def __init__(
        self,
        crew: Any,
        engine: Any,
        config: CrewGovernanceConfig | None = None,
        agent_trust_levels: Optional[dict[str, int]] = None,
    ) -> None:
        self._crew = crew
        self._engine = engine
        self._config: CrewGovernanceConfig = config or CrewGovernanceConfig()
        self._agent_trust_levels: dict[str, int] = agent_trust_levels or {}
        self._task_guard = TaskGuard(engine=engine, config=self._config)
        self._wrap_agents()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def kickoff(self, inputs: Optional[dict[str, Any]] = None) -> Any:
        """
        Execute the governed crew.

        Before handing control to the underlying ``Crew.kickoff``, this method
        evaluates task-level governance checkpoints for each task defined on the
        crew. Tasks whose assigned agent role is denied are either skipped or
        raise ``GovernanceDeniedError`` depending on the configured ``on_denied``
        mode.

        Individual tool calls within task execution are governed by the
        ``GovernedCrewTool`` wrappers already installed on each agent.

        Args:
            inputs: Optional dictionary of inputs forwarded to ``Crew.kickoff``.
                Semantics are determined by the underlying CrewAI crew.

        Returns:
            The result returned by ``Crew.kickoff``. The exact shape depends on
            the crew configuration (e.g., a string, a ``CrewOutput`` object).

        Raises:
            GovernanceDeniedError: When a task governance check fails and
                ``on_denied='raise'``.
        """
        self._check_tasks()
        call_kwargs: dict[str, Any] = {}
        if inputs is not None:
            call_kwargs["inputs"] = inputs
        return self._crew.kickoff(**call_kwargs)

    # ------------------------------------------------------------------
    # Internal: agent wrapping
    # ------------------------------------------------------------------

    def _wrap_agents(self) -> None:
        """
        Replace each agent's tools with ``GovernedCrewTool`` wrappers.

        Trust levels are read from ``agent_trust_levels``. Each agent's role
        string is used as both the governance agent ID and the trust level
        lookup key.

        This method mutates the agent objects held by the inner ``Crew``. The
        original tool objects are preserved inside each ``GovernedCrewTool``
        wrapper and remain accessible via attribute delegation.
        """
        agents = getattr(self._crew, "agents", None)
        if not agents:
            return

        for agent in agents:
            agent_role: str = str(getattr(agent, "role", id(agent)))
            trust_level = self._agent_trust_levels.get(agent_role, 0)

            # Manually set trust level on the engine for this agent.
            # Trust assignment is a one-time, operator-initiated operation.
            self._set_agent_trust(agent_role, trust_level)

            raw_tools: list[Any] = list(getattr(agent, "tools", None) or [])
            if not raw_tools:
                continue

            governed_tools = [
                GovernedCrewTool(
                    tool=tool,
                    engine=self._engine,
                    agent_role=agent_role,
                    config=self._config,
                    required_trust_level=trust_level,
                )
                for tool in raw_tools
            ]
            agent.tools = governed_tools
            logger.debug(
                "GovernedCrew: wrapped %d tool(s) for agent role '%s' (trust_level=%d)",
                len(governed_tools),
                agent_role,
                trust_level,
            )

    def _set_agent_trust(self, agent_role: str, trust_level: int) -> None:
        """
        Set the trust level for an agent role on the governance engine.

        This is a manual, one-time operation performed at crew construction.
        Trust levels are never modified based on runtime behaviour.
        """
        trust_api = getattr(self._engine, "trust", None)
        if trust_api is not None and hasattr(trust_api, "set_level"):
            trust_api.set_level(agent_role, trust_level)
        elif hasattr(self._engine, "set_trust_level"):
            self._engine.set_trust_level(agent_role, trust_level)
        else:
            logger.debug(
                "GovernedCrew: engine does not expose a trust API; "
                "trust_level=%d for '%s' not applied",
                trust_level,
                agent_role,
            )

    # ------------------------------------------------------------------
    # Internal: task-level governance
    # ------------------------------------------------------------------

    def _check_tasks(self) -> None:
        """
        Evaluate task-level governance checkpoints for every task in the crew.

        Tasks are evaluated in definition order. If a task check fails under
        ``on_denied='raise'``, the entire kickoff is aborted via
        ``GovernanceDeniedError``.

        Under ``on_denied='skip'`` the failing task is recorded as a
        ``TaskSkippedError`` in the task's ``output`` attribute (if the
        attribute exists) and execution continues. The underlying CrewAI
        ``Crew.kickoff`` may still attempt to execute the task — governance
        only records the intent to skip at the check phase; actual skipping
        at runtime depends on the crew's task-handling behaviour.

        Under ``on_denied='log'`` the denial is recorded to the audit trail
        and execution continues unchanged.
        """
        tasks = getattr(self._crew, "tasks", None)
        if not tasks:
            return

        for task in tasks:
            agent_role = self._resolve_task_agent_role(task)
            if agent_role is None:
                # Task has no assigned agent — skip governance for this task.
                continue

            try:
                self._task_guard.guard_task(task, agent_role)
            except GovernanceDeniedError:
                raise
            except TaskSkippedError as exc:
                logger.info(
                    "GovernedCrew: task for agent role '%s' skipped: %s",
                    agent_role,
                    exc.reason,
                )

    def _resolve_task_agent_role(self, task: Any) -> Optional[str]:
        """
        Return the role string of the agent assigned to a task.

        Checks ``task.agent.role`` first, then ``task.agent_role``, then
        ``task.agent`` cast to string. Returns None if no agent is discoverable.
        """
        task_agent = getattr(task, "agent", None)
        if task_agent is not None:
            role = getattr(task_agent, "role", None)
            if role is not None:
                return str(role)
            return str(task_agent)

        direct_role = getattr(task, "agent_role", None)
        if direct_role is not None:
            return str(direct_role)

        return None

    # ------------------------------------------------------------------
    # Transparent delegation to the inner crew
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attribute access to the inner crew."""
        return getattr(self._crew, name)

    def __repr__(self) -> str:
        agent_count = len(getattr(self._crew, "agents", []))
        task_count = len(getattr(self._crew, "tasks", []))
        return (
            f"GovernedCrew(agents={agent_count}, tasks={task_count}, "
            f"on_denied={self._config.on_denied.value!r})"
        )
