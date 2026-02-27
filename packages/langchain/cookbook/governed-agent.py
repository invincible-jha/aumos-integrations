# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Governed agent cookbook — full governance on a LangChain agent.

This example wires up a LangChain agent with the AumOS governance callback.
It demonstrates three scenarios in a single run:

1. Query that passes: normal web search at trust level 2.
2. Query that exceeds the static budget: agent tries a high-cost API call.
3. Query requiring higher trust: agent attempts code execution (trust level 3),
   which is denied at the configured trust level 2.

The static spending envelope ($5.00) and trust level are operator-configured
values, not derived from runtime behaviour.

Prerequisites:
    pip install langchain-aumos langchain-openai aumos-governance

Usage:
    python cookbook/governed-agent.py
"""

from __future__ import annotations

import json

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


@tool
def web_search(query: str) -> str:
    """Search the web for current information.

    Args:
        query: The search query.
    """
    return f"[web_search] Top results for '{query}': Python 3.13 released, AumOS 0.2 launched."


@tool
def call_paid_api(endpoint: str, amount: float) -> str:
    """Call a paid external API.  The 'amount' field carries the USD cost.

    Args:
        endpoint: The API endpoint to call.
        amount: Estimated cost in USD for this API call.
    """
    return f"[call_paid_api] Response from {endpoint} (cost: ${amount:.2f})"


@tool
def execute_code(code: str) -> str:
    """Execute Python code and return stdout.  High-risk tool requiring trust level 3.

    Args:
        code: The Python code to execute.
    """
    return f"[execute_code] Output: {code[:60]}"


# ---------------------------------------------------------------------------
# Governance engine setup
# ---------------------------------------------------------------------------

from aumos_governance import GovernanceEngine, GovernanceEngineConfig  # type: ignore[import]
from langchain_aumos import AumOSGovernanceCallback
from langchain_aumos.config import GovernanceConfig
from langchain_aumos.errors import GovernanceDeniedError
from langchain_aumos.types import DeniedAction

# Operator-configured policy: trust level L2, $5.00 static budget.
# These values are set once and never computed from runtime signals.
engine_config = GovernanceEngineConfig(
    agent_id="governed-agent",
    trust_level=2,
    spending_envelope={
        "paid_api": 5.00,       # USD ceiling for paid API calls
        "tool_call": 0.00,      # no direct spend for generic tool calls
    },
)
engine = GovernanceEngine(engine_config)

# Consent is not required for this agent — the operator opted in at deployment.
governance_config = GovernanceConfig(
    agent_id="governed-agent",
    on_denied=DeniedAction.RAISE,
    amount_field="amount",
    scope_mapping={
        "web_search": "tool_call",
        "call_paid_api": "paid_api",
        "execute_code": "tool_call",
    },
    audit_all_calls=True,
    audit_output_preview_length=128,
)

callback = AumOSGovernanceCallback(engine, config=governance_config)

# ---------------------------------------------------------------------------
# Agent setup
# ---------------------------------------------------------------------------

from langchain.agents import AgentExecutor, create_tool_calling_agent  # type: ignore[import]
from langchain_core.prompts import ChatPromptTemplate

llm = ChatOpenAI(model="gpt-4o-mini")
tools = [web_search, call_paid_api, execute_code]

prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a helpful assistant. "
            "Use the tools available to answer questions. "
            "Always pick the most appropriate tool.",
        ),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ]
)

agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(
    agent=agent,
    tools=tools,
    callbacks=[callback],
    verbose=True,
    handle_parsing_errors=True,
)


# ---------------------------------------------------------------------------
# Helper to print a formatted section header
# ---------------------------------------------------------------------------


def section(title: str) -> None:
    """Print a formatted section header to stdout."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ---------------------------------------------------------------------------
# Run the three scenarios
# ---------------------------------------------------------------------------


def run_scenarios() -> None:
    """Execute the three governance scenarios and display the audit trail."""

    # ------------------------------------------------------------------
    # Scenario 1: Normal query — should pass governance (trust L2, no spend)
    # ------------------------------------------------------------------
    section("Scenario 1: Normal web search (expect: ALLOWED)")
    try:
        result = executor.invoke(
            {"input": "What is the latest version of Python?"}
        )
        print(f"Agent output: {result['output']}")
    except GovernanceDeniedError as error:
        print(f"[DENIED] tool='{error.tool_name}' reason='{error.reason}'")

    # ------------------------------------------------------------------
    # Scenario 2: Call paid API over budget — should be denied by engine
    # The static spending envelope is $5.00; the tool carries amount=6.50
    # ------------------------------------------------------------------
    section("Scenario 2: Paid API call exceeding $5.00 budget (expect: DENIED)")
    try:
        result = executor.invoke(
            {
                "input": (
                    "Call the premium data endpoint at /api/v2/premium "
                    "with an estimated cost of $6.50 and return the response."
                )
            }
        )
        print(f"Agent output: {result['output']}")
    except GovernanceDeniedError as error:
        print(f"[DENIED] tool='{error.tool_name}' reason='{error.reason}'")
        print("  Budget enforcement working correctly.")

    # ------------------------------------------------------------------
    # Scenario 3: Code execution at trust level 2 — engine requires L3
    # The engine is configured with trust_level=2; execute_code needs L3.
    # ------------------------------------------------------------------
    section("Scenario 3: Code execution requiring trust level 3 (expect: DENIED)")
    try:
        result = executor.invoke(
            {"input": "Execute this Python: import os; print(os.getcwd())"}
        )
        print(f"Agent output: {result['output']}")
    except GovernanceDeniedError as error:
        print(f"[DENIED] tool='{error.tool_name}' reason='{error.reason}'")
        print("  Trust level enforcement working correctly.")

    # ------------------------------------------------------------------
    # Display the audit trail recorded by the engine
    # ------------------------------------------------------------------
    section("Audit trail")
    if hasattr(engine, "get_audit_trail"):
        trail = engine.get_audit_trail()
        for idx, record in enumerate(trail, start=1):
            status = "ALLOW" if record.get("succeeded") else "DENY"
            tool_name = record.get("tool_name", "unknown")
            print(f"  {idx:2d}. [{status}] {tool_name}")
    else:
        print("  (engine.get_audit_trail() not available — see log output above)")


if __name__ == "__main__":
    run_scenarios()
