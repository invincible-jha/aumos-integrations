# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Quickstart — add AumOS governance to a LangChain agent in 3 lines.

This example shows the minimal integration. The governance callback intercepts
every tool call the agent makes and evaluates it against your governance policy
before execution is allowed to proceed.

Prerequisites:
    pip install langchain-aumos langchain-openai aumos-governance

Usage:
    python examples/quickstart.py
"""

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

# --- Your existing setup ---------------------------------------------------

@tool
def web_search(query: str) -> str:
    """Search the web for information."""
    # Placeholder — replace with a real search tool.
    return f"Search results for: {query}"


@tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression."""
    # Placeholder — replace with a real calculator.
    return f"Result of: {expression}"


llm = ChatOpenAI(model="gpt-4o-mini")
tools = [web_search, calculator]

# --- The 3-line AumOS integration ------------------------------------------

from aumos_governance import GovernanceEngine, GovernanceEngineConfig  # type: ignore[import]
from langchain_aumos import AumOSGovernanceCallback

engine = GovernanceEngine(GovernanceEngineConfig(agent_id="quickstart-agent"))
callback = AumOSGovernanceCallback(engine)

# --- Standard LangChain agent creation — unchanged -------------------------

from langchain.agents import AgentExecutor, create_tool_calling_agent  # type: ignore[import]
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You are a helpful assistant."),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ]
)

agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(
    agent=agent,
    tools=tools,
    callbacks=[callback],   # <-- governance applied here
    verbose=True,
)

# --- Run the agent ---------------------------------------------------------

if __name__ == "__main__":
    from langchain_aumos.errors import GovernanceDeniedError

    try:
        result = executor.invoke({"input": "What is 2 + 2?"})
        print("Agent output:", result["output"])
    except GovernanceDeniedError as error:
        print(f"Tool '{error.tool_name}' was denied by governance: {error.reason}")
