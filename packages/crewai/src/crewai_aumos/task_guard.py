# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
TaskGuard — governance guard for CrewAI task execution.

``TaskGuard`` evaluates governance at the task boundary before an agent is
allowed to begin executing a task. This is the coarse-grained governance layer:
it checks whether a given agent role is permitted to execute a task at all,
independent of which specific tools the task may invoke.

For fine-grained per-tool governance, use ``GovernedCrewTool`` directly.
"""

from __future__ import annotations

import logging
from typing import Any

from .config import CrewGovernanceConfig
from .errors import GovernanceDeniedError
from .types import DeniedAction, GuardResult, TaskContext

logger = logging.getLogger(__name__)


class TaskGuard:
    """
    Governance guard for CrewAI task execution.

    Evaluates a governance checkpoint before each task is dispatched to an
    agent. The governance engine is supplied by the caller — this class is a
    pure adapter between CrewAI task dispatch and the ``aumos-governance`` SDK.

    Args:
        engine: An initialized ``aumos-governance`` ``GovernanceEngine`` instance.
        config: Optional ``CrewGovernanceConfig`` controlling denial handling and
            scope mapping. If omitted, defaults are used.

    Example::

        from crewai_aumos import TaskGuard

        guard = TaskGuard(engine=engine)
        result = guard.guard_task(task, agent_role="researcher")
        if not result.permitted:
            # handle denial
            ...
    """

    def __init__(
        self,
        engine: Any,
        config: CrewGovernanceConfig | None = None,
    ) -> None:
        self._engine = engine
        self._config: CrewGovernanceConfig = config or CrewGovernanceConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def guard_task(self, task: Any, agent_role: str) -> GuardResult:
        """
        Check whether an agent role is permitted to execute the given task.

        Evaluates a synchronous governance checkpoint with the task's scope,
        description, and the executing agent's role. Returns a ``GuardResult``
        describing the decision.

        When ``on_denied`` is ``'raise'``, this method raises
        ``GovernanceDeniedError`` on denial instead of returning a result with
        ``permitted=False``.

        Args:
            task: The CrewAI ``Task`` object to be evaluated. Must expose at
                minimum a ``description`` attribute. A ``tools`` attribute
                (list of tool objects) and an ``expected_output`` attribute are
                used if present.
            agent_role: The role string of the agent that will execute the task.
                Used as the agent identifier in the governance evaluation.

        Returns:
            ``GuardResult`` with ``permitted=True`` if governance allows the task,
            or ``permitted=False`` with a denial reason if governance blocks it
            (only returned when ``on_denied`` is ``'skip'`` or ``'log'``).

        Raises:
            GovernanceDeniedError: When governance denies and ``on_denied='raise'``.
        """
        context = self._build_task_context(task, agent_role)
        decision = self._evaluate_task(context)
        permitted = self._is_allowed(decision)

        if not permitted:
            reason = self._extract_reason(decision)
            self._handle_task_denial(
                task_description=context.task_description,
                agent_role=agent_role,
                reason=reason,
                decision=decision,
            )
            # Only reached when on_denied is SKIP or LOG
            return GuardResult(
                permitted=False,
                reason=reason,
                scope=context.scope,
                agent_role=agent_role,
            )

        self._audit_task(context, succeeded=True)
        return GuardResult(
            permitted=True,
            reason="",
            scope=context.scope,
            agent_role=agent_role,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_task_context(self, task: Any, agent_role: str) -> TaskContext:
        """Extract a ``TaskContext`` from a CrewAI task object."""
        description: str = getattr(task, "description", str(task))
        expected_output: str | None = getattr(task, "expected_output", None)
        scope = self._config.scope_for_task(agent_role)

        tool_names: list[str] = []
        raw_tools = getattr(task, "tools", None)
        if raw_tools:
            for tool_obj in raw_tools:
                name = getattr(tool_obj, "name", None) or getattr(tool_obj, "__name__", None)
                if name:
                    tool_names.append(str(name))

        return TaskContext(
            task_description=description,
            agent_role=agent_role,
            scope=scope,
            expected_output=expected_output,
            tools=tool_names,
        )

    def _evaluate_task(self, context: TaskContext) -> Any:
        """Submit a synchronous governance evaluation for the task context."""
        return self._engine.evaluate_sync(
            agent_id=context.agent_role,
            scope=context.scope,
        )

    def _is_allowed(self, decision: Any) -> bool:
        """Return True if the governance decision permits the task."""
        if hasattr(decision, "allowed"):
            return bool(decision.allowed)
        return bool(decision)

    def _extract_reason(self, decision: Any) -> str:
        """Return a human-readable denial reason from the governance decision."""
        if hasattr(decision, "reason") and decision.reason:
            return str(decision.reason)
        return "governance policy denied this task execution"

    def _handle_task_denial(
        self,
        task_description: str,
        agent_role: str,
        reason: str,
        decision: Any,
    ) -> None:
        """
        Act on a task denial according to the configured ``on_denied`` mode.

        RAISE: Raise ``GovernanceDeniedError``.
        SKIP: Log at INFO level and return (caller receives permitted=False).
        LOG: Log at WARNING level and return (caller receives permitted=False).
        """
        if self._config.on_denied == DeniedAction.RAISE:
            raise GovernanceDeniedError(
                subject=task_description[:120],
                agent_role=agent_role,
                reason=reason,
                decision=decision,
            )
        elif self._config.on_denied == DeniedAction.SKIP:
            logger.info(
                "TaskGuard: task skipped for agent role '%s' (governance denied): %s",
                agent_role,
                reason,
            )
        else:
            # DeniedAction.LOG — record and continue
            logger.warning(
                "TaskGuard: task denied for agent role '%s' (logged, execution continues): %s",
                agent_role,
                reason,
            )

    def _audit_task(self, context: TaskContext, succeeded: bool) -> None:
        """Record a task governance check outcome in the audit trail."""
        if hasattr(self._engine, "record_audit_event"):
            self._engine.record_audit_event(
                agent_id=context.agent_role,
                tool_name=f"task:{context.scope}",
                succeeded=succeeded,
            )
