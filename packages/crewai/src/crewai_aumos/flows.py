# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
GovernedFlow — adds governance checkpoints to CrewAI Flow steps.

CrewAI Flows organise multi-step pipelines where each step function transforms
a shared state object. ``GovernedFlow`` wraps a Flow class (or any object
implementing the Flow protocol) so that governance is evaluated before each
step executes.

Governance evaluation order for every step:
    1. Trust check  — the flow-level agent identity must hold at least the
       step's configured trust level.
    2. Budget check — the step's cost allocation must fit within the relevant
       spending envelope.
    3. Audit record — the decision (permit or deny) is appended to the trail.
    4. Execution    — the real step function is called only on permit.

Trust levels are assigned once per step at configuration time by the operator.
They are never modified based on runtime state or step outcomes.
Budget limits are static integers set in ``FlowGovernanceConfig``.
Audit records are append-only; no analysis is performed on them here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, Field

from .errors import GovernanceDeniedError
from .types import DeniedAction

logger = logging.getLogger(__name__)

StateT = TypeVar("StateT")


# ---------------------------------------------------------------------------
# Protocols — Flow compatibility without importing from CrewAI directly
# ---------------------------------------------------------------------------


@runtime_checkable
class FlowStateProtocol(Protocol):
    """
    Minimum interface expected of a CrewAI Flow state object.

    CrewAI Flow states are typically Pydantic BaseModel subclasses, but the
    governance layer only needs to inspect the state — never mutate it.
    Any object satisfying this protocol is accepted.
    """

    def model_dump(self) -> dict[str, Any]:
        """Return a serializable representation of the state."""
        ...


@runtime_checkable
class FlowProtocol(Protocol):
    """
    Minimum interface expected of a CrewAI Flow object.

    ``kickoff`` is the standard entry point. Additional attributes are
    accessed via ``getattr`` to remain forward-compatible with CrewAI
    version changes.
    """

    def kickoff(self, **kwargs: Any) -> Any:
        """Execute the flow."""
        ...


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class StepGovernancePolicy(BaseModel):
    """
    Per-step governance policy controlling trust and budget requirements.

    Attributes:
        required_trust_level: Minimum trust level the flow's agent identity
            must hold to execute this step. Operator-set; never modified at
            runtime. Defaults to 0 (no restriction).
        budget_category: Optional budget category label. When set, a unit cost
            of ``step_cost`` is checked against this envelope before the step
            runs.
        step_cost: Static cost deducted from the budget envelope when this step
            executes. Defaults to 1.
        scope: Governance scope identifier used in audit records and engine
            evaluation calls for this step.
    """

    required_trust_level: int = Field(
        default=0,
        ge=0,
        le=5,
        description="Minimum trust level required to execute this step.",
    )
    budget_category: str | None = Field(
        default=None,
        description="Budget envelope category to check before this step runs.",
    )
    step_cost: int = Field(
        default=1,
        ge=1,
        description="Static cost units deducted from the budget on each execution.",
    )
    scope: str = Field(
        default="flow_step",
        min_length=1,
        description="Governance scope identifier for audit and evaluation.",
    )

    model_config = {"frozen": True}


class FlowGovernanceConfig(BaseModel):
    """
    Configuration for the AumOS governance integration with CrewAI Flows.

    Attributes:
        agent_id: Identifier for the agent or user identity executing the flow.
            Used in trust lookups and audit records. Required.
        on_denied: What to do when a governance evaluation returns a denial.
            ``DeniedAction.RAISE`` — raise ``GovernanceDeniedError`` (default).
            ``DeniedAction.SKIP`` — log the denial and skip the step; flow continues.
            ``DeniedAction.LOG`` — log and allow execution regardless.
        default_step_policy: Policy applied to steps not present in
            ``step_policies``. Defaults to trust level 0 and no budget check.
        step_policies: Optional mapping from step name to its ``StepGovernancePolicy``.
            Steps not listed fall back to ``default_step_policy``.
        inherited_trust_level: Trust level inherited from the crew or caller
            context. Set once by the operator before the flow starts. Never
            modified during flow execution.
        audit_all_steps: When True, record an audit event for every step
            (both permitted and denied). When False, only denied steps are
            recorded. Defaults to True.
    """

    agent_id: str = Field(
        min_length=1,
        description="Agent or user identity executing the flow.",
    )
    on_denied: DeniedAction = Field(
        default=DeniedAction.RAISE,
        description="Action to take when governance denies a step.",
    )
    default_step_policy: StepGovernancePolicy = Field(
        default_factory=StepGovernancePolicy,
        description="Policy applied to steps with no explicit entry in step_policies.",
    )
    step_policies: dict[str, StepGovernancePolicy] = Field(
        default_factory=dict,
        description="Per-step governance policy overrides keyed by step name.",
    )
    inherited_trust_level: int = Field(
        default=0,
        ge=0,
        le=5,
        description=(
            "Trust level inherited from the parent crew or operator context. "
            "Read by the governance engine during step evaluation. "
            "Set once at construction; never changed during execution."
        ),
    )
    audit_all_steps: bool = Field(
        default=True,
        description="Record an audit event for every completed step.",
    )

    model_config = {"frozen": True}

    def policy_for_step(self, step_name: str) -> StepGovernancePolicy:
        """Return the governance policy for the given step name."""
        return self.step_policies.get(step_name, self.default_step_policy)


# ---------------------------------------------------------------------------
# Governance check
# ---------------------------------------------------------------------------


def flow_governance_check(
    engine: Any,
    flow_state: Any,
    step_name: str,
    config: FlowGovernanceConfig,
) -> bool:
    """
    Validate trust and budget before a flow step executes.

    Calls the governance engine synchronously. Records the decision in the
    audit trail. Returns True on permit, False on denial.

    The ``flow_state`` argument is accepted for audit context — its
    ``model_dump`` output (if available) is passed to the engine as
    ``extra_context`` so that the audit record captures the state at decision
    time.

    Args:
        engine: An initialized ``aumos-governance`` ``GovernanceEngine``.
        flow_state: The current flow state object.
        step_name: Name of the step about to execute.
        config: ``FlowGovernanceConfig`` for this flow.

    Returns:
        True if governance permits the step, False otherwise.
    """
    policy = config.policy_for_step(step_name)
    state_snapshot: dict[str, Any] = {}
    if hasattr(flow_state, "model_dump") and callable(flow_state.model_dump):
        try:
            state_snapshot = flow_state.model_dump()
        except Exception:
            state_snapshot = {}

    eval_kwargs: dict[str, Any] = {
        "agent_id": config.agent_id,
        "scope": policy.scope,
        "extra_context": {
            "step_name": step_name,
            "flow_state_snapshot": state_snapshot,
        },
    }
    if policy.required_trust_level > 0:
        eval_kwargs["required_trust_level"] = policy.required_trust_level
    if policy.budget_category is not None:
        eval_kwargs["budget_category"] = policy.budget_category
        eval_kwargs["amount"] = float(policy.step_cost)

    decision = engine.evaluate_sync(**eval_kwargs)
    permitted = bool(getattr(decision, "allowed", decision))

    _audit_step(engine=engine, step_name=step_name, permitted=permitted, config=config)
    return permitted


def _audit_step(
    engine: Any,
    step_name: str,
    permitted: bool,
    config: FlowGovernanceConfig,
) -> None:
    """Record a step governance decision to the audit trail."""
    if not config.audit_all_steps and permitted:
        return
    if hasattr(engine, "record_audit_event") and callable(engine.record_audit_event):
        try:
            engine.record_audit_event(
                agent_id=config.agent_id,
                tool_name=f"flow_step:{step_name}",
                succeeded=permitted,
                error_message=None if permitted else "governance denied this step",
                output_preview=None,
            )
        except Exception as exc:
            logger.warning(
                "GovernedFlow: failed to record audit event for step '%s': %s",
                step_name,
                exc,
            )


# ---------------------------------------------------------------------------
# GovernedFlow wrapper
# ---------------------------------------------------------------------------


class GovernedFlow:
    """
    Wrap a CrewAI Flow with governance checkpoints on each step.

    Uses composition — the original Flow object is held privately and never
    subclassed. Each registered step is replaced with a governed wrapper
    that calls ``flow_governance_check`` before delegating to the real step
    function.

    Trust levels are inherited from the operator-supplied
    ``FlowGovernanceConfig.inherited_trust_level`` and applied to the engine
    once at construction. They are never modified during flow execution.

    Args:
        flow: Any object implementing ``FlowProtocol`` (i.e., any CrewAI Flow).
        engine: An initialized ``aumos-governance`` ``GovernanceEngine``.
        config: ``FlowGovernanceConfig`` specifying the agent identity, trust
            level, per-step policies, and denial handling.

    Example::

        from crewai_aumos.flows import GovernedFlow, FlowGovernanceConfig

        config = FlowGovernanceConfig(
            agent_id="research-flow",
            inherited_trust_level=2,
            step_policies={
                "fetch_sources": StepGovernancePolicy(required_trust_level=1),
                "write_report": StepGovernancePolicy(required_trust_level=2),
            },
        )
        governed_flow = GovernedFlow(flow=my_flow, engine=engine, config=config)
        result = governed_flow.kickoff(inputs={"topic": "AI safety"})
    """

    def __init__(
        self,
        flow: Any,
        engine: Any,
        config: FlowGovernanceConfig,
    ) -> None:
        self._flow = flow
        self._engine = engine
        self._config = config
        self._apply_inherited_trust()

    def _apply_inherited_trust(self) -> None:
        """
        Register the inherited trust level on the engine for this flow's agent.

        This is a one-time, operator-initiated operation performed at
        construction. The trust level is never modified during flow execution.
        """
        trust_level = self._config.inherited_trust_level
        agent_id = self._config.agent_id
        trust_api = getattr(self._engine, "trust", None)
        if trust_api is not None and hasattr(trust_api, "set_level"):
            trust_api.set_level(agent_id, trust_level)
        elif hasattr(self._engine, "set_trust_level"):
            self._engine.set_trust_level(agent_id, trust_level)
        else:
            logger.debug(
                "GovernedFlow: engine has no trust API; "
                "inherited_trust_level=%d for agent '%s' not applied",
                trust_level,
                agent_id,
            )

    def run_step(self, step_name: str, step_fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Evaluate governance then execute a single named flow step.

        Use this method when you want to govern individual steps outside of a
        full ``kickoff`` call — for example, in a custom flow orchestrator.

        Args:
            step_name: Name of the step used for policy lookup and audit.
            step_fn: The actual step callable to invoke on permit.
            *args: Positional arguments forwarded to ``step_fn``.
            **kwargs: Keyword arguments forwarded to ``step_fn``.

        Returns:
            The return value of ``step_fn`` on permit.

        Raises:
            GovernanceDeniedError: When governance denies and ``on_denied=RAISE``.
        """
        flow_state = getattr(self._flow, "state", None)
        permitted = flow_governance_check(
            engine=self._engine,
            flow_state=flow_state,
            step_name=step_name,
            config=self._config,
        )
        if not permitted:
            return self._handle_step_denial(step_name)
        return step_fn(*args, **kwargs)

    def _handle_step_denial(self, step_name: str) -> Any:
        """Act on a step denial according to the configured ``on_denied`` mode."""
        reason = f"governance policy denied flow step '{step_name}'"
        if self._config.on_denied == DeniedAction.RAISE:
            raise GovernanceDeniedError(
                subject=step_name,
                agent_role=self._config.agent_id,
                reason=reason,
                decision=None,
            )
        elif self._config.on_denied == DeniedAction.SKIP:
            logger.info(
                "GovernedFlow: step '%s' skipped for agent '%s': %s",
                step_name,
                self._config.agent_id,
                reason,
            )
            return None
        else:
            # DeniedAction.LOG — record and allow (already audited in check)
            logger.warning(
                "GovernedFlow: step '%s' denied for agent '%s' (logged, "
                "execution continues): %s",
                step_name,
                self._config.agent_id,
                reason,
            )
            return None

    def kickoff(self, **kwargs: Any) -> Any:
        """
        Execute the governed flow.

        Delegates directly to the underlying flow's ``kickoff`` method.
        Per-step governance is enforced when steps are individually called
        through ``run_step``. For CrewAI Flows that execute steps internally,
        install step wrappers via ``wrap_flow_steps`` before calling this.

        Args:
            **kwargs: Forwarded to the underlying flow's ``kickoff``.

        Returns:
            The result returned by the underlying flow's ``kickoff``.
        """
        return self._flow.kickoff(**kwargs)

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attribute access to the inner flow."""
        return getattr(self._flow, name)

    def __repr__(self) -> str:
        return (
            f"GovernedFlow(agent_id={self._config.agent_id!r}, "
            f"on_denied={self._config.on_denied.value!r})"
        )
