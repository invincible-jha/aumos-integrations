# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
LangGraph governance node example.

Minimal 3-node graph demonstrating ``GovernanceNode`` integration:

    input_node → governance_node → response_node
                      ↓ (blocked)
                  deny_node

The governance node reads ``trust_level`` and ``spend_amount`` from the agent
state, evaluates them against the static policy configured in
``GovernanceNodeConfig``, and sets ``governance_blocked`` in the state.

A conditional edge routes to ``deny_node`` when blocked, or ``response_node``
when allowed.

Prerequisites:
    pip install langchain-aumos langgraph aumos-governance

Usage:
    python examples/langgraph-example.py
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph  # type: ignore[import]

from aumos_governance import GovernanceEngine, GovernanceEngineConfig  # type: ignore[import]
from langchain_aumos.langgraph_node import GovernanceNodeConfig, create_governance_node

# ---------------------------------------------------------------------------
# Agent state schema
# ---------------------------------------------------------------------------


class AgentState(TypedDict, total=False):
    """Shared state dict passed between LangGraph nodes."""

    query: str
    trust_level: int
    spend_amount: float
    consent_granted: bool
    governance_blocked: bool
    governance_denial_reason: str
    response: str


# ---------------------------------------------------------------------------
# Governance engine — operator-configured static policy
# ---------------------------------------------------------------------------

engine = GovernanceEngine(
    GovernanceEngineConfig(
        agent_id="langgraph-demo",
        trust_level=2,
        spending_envelope={"graph_node": 5.00},
    )
)

governance_config = GovernanceNodeConfig(
    agent_id="langgraph-demo",
    required_trust_level=2,     # static minimum — operator sets this once
    spending_limit=5.00,        # static ceiling — never derived from signals
    require_consent=False,
    scope="graph_node",
    audit_decisions=True,
)

governance_node = create_governance_node(engine, governance_config)

# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


def input_node(state: AgentState) -> AgentState:
    """Pass-through node that represents the entry point of the graph."""
    print(f"  [input_node] query='{state.get('query')}' "
          f"trust={state.get('trust_level')} "
          f"spend={state.get('spend_amount')}")
    return {}


def response_node(state: AgentState) -> AgentState:
    """Generate a response when governance has allowed execution."""
    query = state.get("query", "")
    response = f"[response_node] Answered: '{query}'"
    print(f"  [response_node] {response}")
    return {"response": response}


def deny_node(state: AgentState) -> AgentState:
    """Return a denial message when governance has blocked execution."""
    reason = state.get("governance_denial_reason", "governance policy denied request")
    response = f"[deny_node] Request blocked — {reason}"
    print(f"  [deny_node] {response}")
    return {"response": response}


def route_on_governance(state: AgentState) -> str:
    """Conditional edge: route to 'blocked' or 'allowed' based on governance state."""
    if state.get("governance_blocked"):
        return "blocked"
    return "allowed"


# ---------------------------------------------------------------------------
# Build the StateGraph
# ---------------------------------------------------------------------------

graph_builder = StateGraph(AgentState)

graph_builder.add_node("input", input_node)
graph_builder.add_node("governance", governance_node)
graph_builder.add_node("response", response_node)
graph_builder.add_node("deny", deny_node)

graph_builder.set_entry_point("input")
graph_builder.add_edge("input", "governance")
graph_builder.add_conditional_edges(
    "governance",
    route_on_governance,
    {"allowed": "response", "blocked": "deny"},
)
graph_builder.add_edge("response", END)
graph_builder.add_edge("deny", END)

graph = graph_builder.compile()

# ---------------------------------------------------------------------------
# Run two scenarios
# ---------------------------------------------------------------------------


def section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'=' * 55}")
    print(f"  {title}")
    print(f"{'=' * 55}")


if __name__ == "__main__":
    # Scenario 1: trust level meets requirement, spend within budget — allowed.
    section("Scenario 1: Governance ALLOWS execution")
    result = graph.invoke(
        {
            "query": "Summarise Q4 revenue",
            "trust_level": 2,
            "spend_amount": 1.00,
        }
    )
    print(f"  Final response: {result.get('response')}")

    # Scenario 2: spend exceeds static budget — blocked by governance node.
    section("Scenario 2: Governance BLOCKS (budget exceeded)")
    result = graph.invoke(
        {
            "query": "Run full dataset analysis",
            "trust_level": 2,
            "spend_amount": 9.99,
        }
    )
    print(f"  Final response: {result.get('response')}")

    # Scenario 3: trust level below the static minimum — blocked.
    section("Scenario 3: Governance BLOCKS (trust level too low)")
    result = graph.invoke(
        {
            "query": "Execute sensitive operation",
            "trust_level": 1,
            "spend_amount": 0.50,
        }
    )
    print(f"  Final response: {result.get('response')}")
