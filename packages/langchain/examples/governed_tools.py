# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Governed tools — wrap individual LangChain tools with per-tool governance gates.

Use ``GovernedTool`` (or the ``govern()`` shorthand) when you need different
governance requirements per tool. For example: a web search tool may be
permitted at trust level 1, while a code execution tool requires trust level 3.

This is complementary to ``AumOSGovernanceCallback``. You can use both together
(the callback provides a uniform gate; ``GovernedTool`` adds per-tool gates on top),
or use ``GovernedTool`` alone without any callback.

Prerequisites:
    pip install langchain-aumos langchain-openai aumos-governance

Usage:
    python examples/governed_tools.py
"""

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

# --- Define some tools with different risk profiles -----------------------

@tool
def web_search(query: str) -> str:
    """Search the web for recent information."""
    return f"[web_search] results for: {query}"


@tool
def read_file(path: str) -> str:
    """Read the contents of a file."""
    return f"[read_file] contents of: {path}"


@tool
def execute_code(code: str) -> str:
    """Execute Python code and return stdout."""
    return f"[execute_code] output of: {code[:50]}"


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email to an address."""
    return f"[send_email] sent to {to}"


# --- Wrap each tool with its own governance requirements ------------------

from aumos_governance import GovernanceEngine, GovernanceEngineConfig  # type: ignore[import]
from langchain_aumos import GovernedTool, govern
from langchain_aumos.types import DeniedAction

engine = GovernanceEngine(
    GovernanceEngineConfig(agent_id="governed-tools-example")
)

# web_search — low risk, trust level 1 sufficient, skip if denied
safe_search = GovernedTool(
    tool=web_search,
    engine=engine,
    required_trust_level=1,
    budget_category="web_requests",
    on_denied=DeniedAction.SKIP,
    agent_id="governed-tools-example",
)

# read_file — moderate risk, trust level 2, raise on denial
safe_read = govern(
    tool=read_file,
    engine=engine,
    required_trust_level=2,
    on_denied=DeniedAction.RAISE,
    agent_id="governed-tools-example",
)

# execute_code — high risk, trust level 3, raise on denial
safe_execute = govern(
    tool=execute_code,
    engine=engine,
    required_trust_level=3,
    on_denied=DeniedAction.RAISE,
    agent_id="governed-tools-example",
)

# send_email — external action, trust level 3, raise on denial
safe_email = GovernedTool(
    tool=send_email,
    engine=engine,
    required_trust_level=3,
    budget_category="outbound_comms",
    on_denied=DeniedAction.RAISE,
    agent_id="governed-tools-example",
)

# --- Build an agent using only the governed tool wrappers -----------------

from langchain.agents import AgentExecutor, create_tool_calling_agent  # type: ignore[import]
from langchain_core.prompts import ChatPromptTemplate

llm = ChatOpenAI(model="gpt-4o-mini")

governed_tools = [safe_search, safe_read, safe_execute, safe_email]

prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an assistant. Use tools as needed. "
            "Do not use a tool if it is not necessary.",
        ),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ]
)

agent = create_tool_calling_agent(llm, governed_tools, prompt)
executor = AgentExecutor(agent=agent, tools=governed_tools, verbose=True)

# --- Run ------------------------------------------------------------------

if __name__ == "__main__":
    from langchain_aumos.errors import GovernanceDeniedError

    # This call will be evaluated against each tool's governance requirements.
    try:
        result = executor.invoke(
            {"input": "Search the web for the latest Python release notes."}
        )
        print("Agent output:", result["output"])
    except GovernanceDeniedError as error:
        print(f"Governance denied '{error.tool_name}': {error.reason}")
