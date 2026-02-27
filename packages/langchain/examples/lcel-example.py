# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
LCEL governance step example.

Minimal demonstration of ``GovernanceRunnable`` composed into a LangChain
Expression Language pipe using the ``|`` operator:

    prompt | llm | governance_step | output_parser

``GovernanceRunnable`` sits between the LLM output and the output parser.
When governance denies, it raises ``GovernanceDeniedError`` before the parser
runs.  When governance allows, the LLM message is passed through unchanged.

This example shows:
1. A passing invocation (trust level and budget within policy).
2. A denied invocation (spend amount exceeds the static ceiling).

Prerequisites:
    pip install langchain-aumos langchain-openai aumos-governance

Usage:
    python examples/lcel-example.py
"""

from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from aumos_governance import GovernanceEngine, GovernanceEngineConfig  # type: ignore[import]
from langchain_aumos.errors import GovernanceDeniedError
from langchain_aumos.lcel_step import GovernanceRunnable, GovernanceRunnableConfig
from langchain_aumos.types import DeniedAction

# ---------------------------------------------------------------------------
# Governance engine — static policy, operator-configured once
# ---------------------------------------------------------------------------

engine = GovernanceEngine(
    GovernanceEngineConfig(
        agent_id="lcel-demo",
        trust_level=2,
        spending_envelope={"lcel_step": 5.00},
    )
)

# ---------------------------------------------------------------------------
# Governance step
# ---------------------------------------------------------------------------

# The governance runnable enforces:
#   • required_trust_level=2  (static >= comparison)
#   • spending_limit=5.00     (static <= comparison on spend_amount input key)
# on_denied='raise' stops the pipe immediately with GovernanceDeniedError.
governance_step = GovernanceRunnable(
    engine,
    GovernanceRunnableConfig(
        agent_id="lcel-demo",
        required_trust_level=2,
        spending_limit=5.00,
        scope="lcel_step",
        on_denied=DeniedAction.RAISE,
        spend_amount_key="spend_amount",
    ),
)

# ---------------------------------------------------------------------------
# Build the LCEL chain with the pipe operator
# ---------------------------------------------------------------------------

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You are a concise assistant. Reply in one sentence."),
        ("human", "{question}"),
    ]
)

llm = ChatOpenAI(model="gpt-4o-mini")

# governance_step is between llm and parser — it receives the AIMessage from
# the LLM, evaluates governance using context from the chain input, and passes
# the message through on allow.
chain = prompt | llm | governance_step | StrOutputParser()

# ---------------------------------------------------------------------------
# Run scenarios
# ---------------------------------------------------------------------------


def section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'=' * 55}")
    print(f"  {title}")
    print(f"{'=' * 55}")


if __name__ == "__main__":
    # Scenario 1: spend within the static $5.00 ceiling — chain completes.
    section("Scenario 1: Governance ALLOWS (spend within budget)")
    try:
        # The spend_amount key is forwarded through the chain as extra context.
        # GovernanceRunnable reads it when evaluating the budget check.
        response = chain.invoke(
            {
                "question": "What is 2 + 2?",
                "spend_amount": 0.10,
            }
        )
        print(f"Response: {response}")
    except GovernanceDeniedError as error:
        print(f"[DENIED] scope='{error.tool_name}' reason='{error.reason}'")

    # Scenario 2: spend exceeds the static $5.00 ceiling — chain is blocked.
    section("Scenario 2: Governance BLOCKS (spend exceeds static ceiling)")
    try:
        response = chain.invoke(
            {
                "question": "Generate a 10,000-word analysis report.",
                "spend_amount": 8.75,   # exceeds the operator-set $5.00 limit
            }
        )
        print(f"Response: {response}")
    except GovernanceDeniedError as error:
        print(f"[DENIED] scope='{error.tool_name}' reason='{error.reason}'")
        print("  Budget enforcement working correctly.")

    # Scenario 3: async invocation — governance works identically over ainvoke.
    section("Scenario 3: Async invocation (governance ALLOWS)")
    import asyncio

    async def run_async() -> None:
        """Run the chain asynchronously to verify ainvoke compatibility."""
        try:
            response = await chain.ainvoke(
                {
                    "question": "Explain Python type hints briefly.",
                    "spend_amount": 0.25,
                }
            )
            print(f"Async response: {response}")
        except GovernanceDeniedError as error:
            print(f"[DENIED] scope='{error.tool_name}' reason='{error.reason}'")

    asyncio.run(run_async())
