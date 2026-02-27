# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
LangGraph governance node for AumOS.

Insert a ``GovernanceNode`` into any LangGraph ``StateGraph`` to enforce trust,
budget, and consent checks at any point in the graph.  The node reads standard
fields from the agent state dict, evaluates governance via the ``aumos-governance``
engine, and returns an updated state.  When a check fails the node sets
``governance_blocked: True`` and records a ``governance_denial_reason`` — it never
raises inside the graph so downstream conditional edges can route cleanly.

Typical usage::

    from langchain_aumos.langgraph_node import create_governance_node, GovernanceNodeConfig

    config = GovernanceNodeConfig(agent_id="my-agent", required_trust_level=2)
    gov_node = create_governance_node(engine, config)

    graph = StateGraph(AgentState)
    graph.add_node("governance", gov_node)
    graph.add_edge("input", "governance")
    graph.add_conditional_edges(
        "governance",
        lambda state: "blocked" if state.get("governance_blocked") else "respond",
        {"blocked": "deny_response", "respond": "llm"},
    )
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration model
# ---------------------------------------------------------------------------


class GovernanceNodeConfig(BaseModel):
    """
    Configuration for a LangGraph governance node.

    Attributes:
        agent_id: Agent identifier passed to every governance evaluation.
        required_trust_level: Minimum static trust level required to pass the
            trust check.  Trust is set manually by operators — this is a
            ``>=`` comparison only.
        spending_limit: Static per-invocation spending ceiling in USD.  The
            node reads ``spend_amount`` from the state dict and compares with
            ``<=``.  When ``None`` the budget check is skipped entirely.
        require_consent: When ``True`` the node reads ``consent_granted`` from
            the state dict and denies if the value is falsy.
        scope: Governance scope string forwarded to the engine evaluation call.
        audit_decisions: When ``True`` the node calls
            ``engine.record_audit_event()`` after every evaluation (both
            allow and deny).
        state_trust_key: Key in the agent state dict that holds the current
            trust level integer.  Defaults to ``'trust_level'``.
        state_spend_key: Key in the agent state dict that holds the current
            spend amount float.  Defaults to ``'spend_amount'``.
        state_consent_key: Key in the agent state dict that holds the consent
            boolean.  Defaults to ``'consent_granted'``.
    """

    agent_id: str = Field(default="default", min_length=1)
    required_trust_level: int = Field(default=0, ge=0)
    spending_limit: float | None = Field(default=None, ge=0.0)
    require_consent: bool = Field(default=False)
    scope: str = Field(default="graph_node", min_length=1)
    audit_decisions: bool = Field(default=True)
    state_trust_key: str = Field(default="trust_level")
    state_spend_key: str = Field(default="spend_amount")
    state_consent_key: str = Field(default="consent_granted")

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class NodeDecision(BaseModel):
    """
    The outcome of a governance node evaluation.

    Attributes:
        allowed: True when all checks pass and execution may continue.
        reason: Human-readable explanation, populated on denial.
        trust_level: Trust level read from state (for audit annotations).
        budget_remaining: Budget remaining after this evaluation step; present
            only when a spending limit is configured.
        consent_status: Consent status read from state.
    """

    allowed: bool
    reason: str = ""
    trust_level: int = 0
    budget_remaining: float | None = None
    consent_status: bool = True


# ---------------------------------------------------------------------------
# GovernanceNode
# ---------------------------------------------------------------------------


class GovernanceNode:
    """
    LangGraph node that enforces AumOS governance checks.

    Designed to be inserted into a ``StateGraph`` via ``add_node()``.  The
    node is callable — ``__call__(state)`` — which is the interface LangGraph
    expects.

    Checks are performed in this order:
    1. Consent check (if ``require_consent=True``).
    2. Trust level check (static ``>=`` comparison).
    3. Budget check (static ``<=`` comparison, if ``spending_limit`` is set).
    4. Engine evaluation (delegates remaining policy to the governance engine).

    The first failing check short-circuits evaluation and sets
    ``governance_blocked: True`` in the returned state patch.

    Args:
        engine: An initialized ``aumos-governance`` ``GovernanceEngine``.
        config: ``GovernanceNodeConfig`` controlling all check parameters.
    """

    def __init__(self, engine: Any, config: GovernanceNodeConfig) -> None:
        self._engine = engine
        self._config = config

    # ------------------------------------------------------------------
    # LangGraph callable interface
    # ------------------------------------------------------------------

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Evaluate governance against the current agent state.

        Reads governance-relevant fields from ``state``, runs all configured
        checks, and returns a state patch dict.  The patch always contains
        ``governance_blocked`` (bool) and ``governance_denial_reason`` (str).
        On allow, both fields are set to their cleared values.

        Args:
            state: The current LangGraph agent state dict.

        Returns:
            A dict of state updates to merge into the graph state.
        """
        decision = self._evaluate(state)
        self._maybe_audit(state, decision)

        if decision.allowed:
            logger.debug(
                "GovernanceNode: allowed (agent='%s', scope='%s')",
                self._config.agent_id,
                self._config.scope,
            )
            return {
                "governance_blocked": False,
                "governance_denial_reason": "",
            }

        logger.info(
            "GovernanceNode: blocked (agent='%s', scope='%s', reason='%s')",
            self._config.agent_id,
            self._config.scope,
            decision.reason,
        )
        return {
            "governance_blocked": True,
            "governance_denial_reason": decision.reason,
        }

    # ------------------------------------------------------------------
    # Evaluation logic
    # ------------------------------------------------------------------

    def _evaluate(self, state: dict[str, Any]) -> NodeDecision:
        """Run all governance checks and return a ``NodeDecision``."""
        trust_level = self._read_trust(state)
        spend_amount = self._read_spend(state)
        consent_status = self._read_consent(state)

        # 1. Consent check
        if self._config.require_consent and not consent_status:
            return NodeDecision(
                allowed=False,
                reason="consent not granted for this operation",
                trust_level=trust_level,
                consent_status=consent_status,
            )

        # 2. Static trust level check (manual comparison only)
        if trust_level < self._config.required_trust_level:
            return NodeDecision(
                allowed=False,
                reason=(
                    f"trust level {trust_level} is below the required level "
                    f"{self._config.required_trust_level} for scope '{self._config.scope}'"
                ),
                trust_level=trust_level,
                consent_status=consent_status,
            )

        # 3. Static budget check (no adaptive logic)
        budget_remaining: float | None = None
        if self._config.spending_limit is not None and spend_amount is not None:
            budget_remaining = self._config.spending_limit - spend_amount
            if spend_amount > self._config.spending_limit:
                return NodeDecision(
                    allowed=False,
                    reason=(
                        f"spend amount {spend_amount:.4f} exceeds the static "
                        f"limit of {self._config.spending_limit:.4f} "
                        f"for scope '{self._config.scope}'"
                    ),
                    trust_level=trust_level,
                    budget_remaining=budget_remaining,
                    consent_status=consent_status,
                )

        # 4. Engine evaluation — remaining policy decisions delegated to engine
        engine_decision = self._call_engine(
            trust_level=trust_level,
            spend_amount=spend_amount,
        )
        if not self._is_allowed(engine_decision):
            return NodeDecision(
                allowed=False,
                reason=self._extract_reason(engine_decision),
                trust_level=trust_level,
                budget_remaining=budget_remaining,
                consent_status=consent_status,
            )

        return NodeDecision(
            allowed=True,
            trust_level=trust_level,
            budget_remaining=budget_remaining,
            consent_status=consent_status,
        )

    def _call_engine(
        self,
        trust_level: int,
        spend_amount: float | None,
    ) -> Any:
        """Delegate to the governance engine for policy evaluation."""
        eval_kwargs: dict[str, Any] = {
            "agent_id": self._config.agent_id,
            "scope": self._config.scope,
            "required_trust_level": self._config.required_trust_level,
        }
        if spend_amount is not None:
            eval_kwargs["amount"] = spend_amount
        return self._engine.evaluate_sync(**eval_kwargs)

    # ------------------------------------------------------------------
    # State field readers
    # ------------------------------------------------------------------

    def _read_trust(self, state: dict[str, Any]) -> int:
        """Read the trust level integer from agent state."""
        raw = state.get(self._config.state_trust_key, 0)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    def _read_spend(self, state: dict[str, Any]) -> float | None:
        """Read the spend amount float from agent state, or None if absent."""
        raw = state.get(self._config.state_spend_key)
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def _read_consent(self, state: dict[str, Any]) -> bool:
        """Read the consent flag from agent state."""
        return bool(state.get(self._config.state_consent_key, False))

    # ------------------------------------------------------------------
    # Decision helpers
    # ------------------------------------------------------------------

    def _is_allowed(self, decision: Any) -> bool:
        """Return True if the engine decision permits execution."""
        if hasattr(decision, "allowed"):
            return bool(decision.allowed)
        return bool(decision)

    def _extract_reason(self, decision: Any) -> str:
        """Return a human-readable denial reason from an engine decision."""
        if hasattr(decision, "reason") and decision.reason:
            return str(decision.reason)
        return "governance engine denied this graph node execution"

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def _maybe_audit(self, state: dict[str, Any], decision: NodeDecision) -> None:
        """Record the governance decision to the audit trail when enabled."""
        if not self._config.audit_decisions:
            return
        if not hasattr(self._engine, "record_audit_event"):
            logger.debug(
                "Audit: scope='%s' agent='%s' allowed=%s",
                self._config.scope,
                self._config.agent_id,
                decision.allowed,
            )
            return
        self._engine.record_audit_event(
            agent_id=self._config.agent_id,
            tool_name=self._config.scope,
            succeeded=decision.allowed,
            error_message=decision.reason if not decision.allowed else None,
        )


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


def create_governance_node(
    engine: Any,
    config: GovernanceNodeConfig | None = None,
    *,
    agent_id: str = "default",
    required_trust_level: int = 0,
    spending_limit: float | None = None,
    require_consent: bool = False,
    scope: str = "graph_node",
    audit_decisions: bool = True,
) -> GovernanceNode:
    """
    Factory that returns a ``GovernanceNode`` callable for use with
    ``StateGraph.add_node()``.

    You may either pass a fully-specified ``GovernanceNodeConfig`` or use the
    keyword arguments as a convenience shorthand.  When ``config`` is provided,
    keyword arguments are ignored.

    Args:
        engine: Initialized ``aumos-governance`` ``GovernanceEngine``.
        config: Optional fully-specified ``GovernanceNodeConfig``.
        agent_id: Agent identifier.
        required_trust_level: Minimum static trust level (manual ``>=`` check).
        spending_limit: Static per-invocation spending ceiling in USD.
        require_consent: Require ``consent_granted=True`` in state.
        scope: Governance scope string.
        audit_decisions: Record every evaluation to the audit trail.

    Returns:
        A ``GovernanceNode`` instance callable as a LangGraph node.

    Example::

        gov_node = create_governance_node(
            engine,
            agent_id="rag-agent",
            required_trust_level=2,
            spending_limit=5.00,
            require_consent=True,
        )
        graph.add_node("governance", gov_node)
    """
    resolved_config = config or GovernanceNodeConfig(
        agent_id=agent_id,
        required_trust_level=required_trust_level,
        spending_limit=spending_limit,
        require_consent=require_consent,
        scope=scope,
        audit_decisions=audit_decisions,
    )
    return GovernanceNode(engine=engine, config=resolved_config)
