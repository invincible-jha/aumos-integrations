# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Budget-controlled agent — enforce spending limits on LangChain tool calls.

This example shows how to configure the AumOS governance callback to track and
enforce spending limits. When a tool call carries a spend amount (extracted from
the tool's JSON input), the governance engine checks it against the static
spending envelope defined in the engine configuration.

The spending envelope is defined once, at engine initialization, by the operator.
It is never computed from runtime signals.

Prerequisites:
    pip install langchain-aumos langchain-openai aumos-governance

Usage:
    python examples/budget_controlled.py
"""

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

# --- Define tools that carry spend amounts in their inputs ----------------

@tool
def call_llm_api(prompt: str, amount: float) -> str:
    """
    Call an external LLM API. The ``amount`` field represents the estimated
    cost in USD for this API call.

    Args:
        prompt: The text to send to the API.
        amount: Estimated cost in USD.
    """
    return f"[llm_api] response to: {prompt[:50]}... (cost: ${amount:.4f})"


@tool
def query_database(sql: str, amount: float) -> str:
    """
    Run a SQL query against the data warehouse. The ``amount`` field represents
    the estimated compute cost in USD.

    Args:
        sql: The SQL query to execute.
        amount: Estimated compute cost in USD.
    """
    return f"[database] results for: {sql[:50]}... (cost: ${amount:.4f})"


@tool
def send_notification(channel: str, message: str) -> str:
    """
    Send a notification. Zero spend amount — this tool is free.

    Args:
        channel: The notification channel (e.g., 'slack', 'email').
        message: The notification body.
    """
    return f"[notification] sent to {channel}"


# --- Configure the governance engine with a static spending envelope ------

from aumos_governance import GovernanceEngine, GovernanceEngineConfig  # type: ignore[import]
from langchain_aumos import AumOSGovernanceCallback
from langchain_aumos.config import GovernanceConfig
from langchain_aumos.types import DeniedAction

# The spending envelope is set by the operator at configuration time.
# It is a fixed policy value — never derived from runtime behavior.
engine_config = GovernanceEngineConfig(
    agent_id="budget-agent",
    spending_envelope={
        "llm_api_calls": 0.50,    # USD limit for LLM API spend
        "database_queries": 0.10, # USD limit for database query spend
    },
)
engine = GovernanceEngine(engine_config)

# Configure the integration to extract the 'amount' field from tool JSON inputs
# and map tool names to their budget categories.
governance_config = GovernanceConfig(
    agent_id="budget-agent",
    on_denied=DeniedAction.RAISE,
    amount_field="amount",
    scope_mapping={
        "call_llm_api": "llm_api_calls",
        "query_database": "database_queries",
        "send_notification": "free_tier",
    },
    audit_all_calls=True,
)

callback = AumOSGovernanceCallback(engine, config=governance_config)

# --- Build the agent ------------------------------------------------------

from langchain.agents import AgentExecutor, create_tool_calling_agent  # type: ignore[import]
from langchain_core.prompts import ChatPromptTemplate

llm = ChatOpenAI(model="gpt-4o-mini")
tools = [call_llm_api, query_database, send_notification]

prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a data analysis assistant with a strict cost budget. "
            "Every LLM API call and database query has a cost. "
            "Be efficient and avoid unnecessary tool calls.",
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
)

# --- Run ------------------------------------------------------------------

if __name__ == "__main__":
    from langchain_aumos.errors import GovernanceDeniedError

    print("Running budget-controlled agent...")
    print("Spending envelope: LLM API = $0.50, Database = $0.10")
    print()

    try:
        result = executor.invoke(
            {
                "input": (
                    "Analyse Q4 revenue by region. "
                    "Query the database and summarize the findings."
                )
            }
        )
        print("Agent output:", result["output"])
    except GovernanceDeniedError as error:
        print()
        print(f"Budget limit reached — tool '{error.tool_name}' was denied.")
        print(f"Reason: {error.reason}")
        print("The agent has been stopped to prevent budget overrun.")
