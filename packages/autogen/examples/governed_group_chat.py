# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Governed group chat — apply per-agent governance across an AutoGen GroupChat.

This example shows how to govern multiple agents in an AutoGen ``GroupChat``.
Each agent is wrapped with ``GovernedConversableAgent`` at a different trust
level. ``MessageGuard`` is also used standalone to evaluate governance on the
group chat manager's message routing decisions.

Trust levels are assigned manually by the operator — never computed.

Prerequisites:
    pip install autogen-aumos pyautogen aumos-governance

Usage:
    python examples/governed_group_chat.py
"""

import autogen  # type: ignore[import]

# --- Define functions used by the agents ------------------------------------

def web_search(query: str) -> str:
    """Search the web. Restricted to research_agent (trust level 2+)."""
    return f"[web_search] Results for: {query}"


def write_to_database(table: str, payload: str) -> str:
    """Write data to the database. Restricted to data_agent (trust level 3)."""
    return f"[database] Written to {table}: {payload[:60]}..."


def summarise(text: str) -> str:
    """Summarise text. Available to all agents (trust level 1+)."""
    return f"[summarise] {text[:120]}..."


# --- LLM config (shared) ----------------------------------------------------

llm_config_base = {
    "config_list": [{"model": "gpt-4o-mini", "api_key": "YOUR_API_KEY"}],
}

# --- Build AutoGen agents ---------------------------------------------------

research_agent = autogen.ConversableAgent(
    name="research_agent",
    system_message=(
        "You are a researcher. You search for information and summarise findings."
    ),
    llm_config={
        **llm_config_base,
        "functions": [
            {
                "name": "web_search",
                "description": "Search the web for information.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query."}
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "summarise",
                "description": "Summarise a block of text.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to summarise."}
                    },
                    "required": ["text"],
                },
            },
        ],
    },
    function_map={"web_search": web_search, "summarise": summarise},
)

data_agent = autogen.ConversableAgent(
    name="data_agent",
    system_message=(
        "You are a data manager. You store research findings in the database."
    ),
    llm_config={
        **llm_config_base,
        "functions": [
            {
                "name": "write_to_database",
                "description": "Write structured data to the database.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "table": {"type": "string"},
                        "payload": {"type": "string"},
                    },
                    "required": ["table", "payload"],
                },
            },
            {
                "name": "summarise",
                "description": "Summarise a block of text.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to summarise."}
                    },
                    "required": ["text"],
                },
            },
        ],
    },
    function_map={"write_to_database": write_to_database, "summarise": summarise},
)

summary_agent = autogen.ConversableAgent(
    name="summary_agent",
    system_message="You produce concise summaries of research findings.",
    llm_config={
        **llm_config_base,
        "functions": [
            {
                "name": "summarise",
                "description": "Summarise a block of text.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to summarise."}
                    },
                    "required": ["text"],
                },
            },
        ],
    },
    function_map={"summarise": summarise},
)

# --- Governance engine and config -------------------------------------------

from aumos_governance import GovernanceEngine, GovernanceEngineConfig  # type: ignore[import]
from autogen_aumos import GovernedConversableAgent
from autogen_aumos.config import AutoGenGovernanceConfig
from autogen_aumos.message_guard import MessageGuard
from autogen_aumos.types import DeniedAction

engine = GovernanceEngine(GovernanceEngineConfig())

governance_config = AutoGenGovernanceConfig(
    on_denied=DeniedAction.RAISE,
    tool_scope_mapping={
        "web_search": "tool:web_access",
        "write_to_database": "tool:database_write",
        "summarise": "tool:summarise",
    },
    recipient_scope_mapping={
        "data_agent": "message:data_channel",
        "research_agent": "message:research_channel",
        "summary_agent": "message:summary_channel",
    },
    audit_all_actions=True,
)

# Trust levels are assigned manually by the operator.
# summary_agent: trust level 1 — can only summarise
# research_agent: trust level 2 — can search and summarise
# data_agent: trust level 3 — can write to the database
governed_research = GovernedConversableAgent(
    agent=research_agent,
    engine=engine,
    trust_level=2,
    config=governance_config,
)

governed_data = GovernedConversableAgent(
    agent=data_agent,
    engine=engine,
    trust_level=3,
    config=governance_config,
)

governed_summary = GovernedConversableAgent(
    agent=summary_agent,
    engine=engine,
    trust_level=1,
    config=governance_config,
)

# --- A standalone MessageGuard for the group chat manager's routing ---------
# The group chat manager routes messages between agents. We apply a message
# guard here to ensure that the routing itself is governed.
message_guard = MessageGuard(engine=engine, config=governance_config)

# --- Build the group chat using the governed agents' inner agent objects ----

group_chat = autogen.GroupChat(
    agents=[
        governed_research.agent,
        governed_data.agent,
        governed_summary.agent,
    ],
    messages=[],
    max_round=6,
)

manager = autogen.GroupChatManager(
    groupchat=group_chat,
    llm_config=llm_config_base,
)

user_proxy = autogen.UserProxyAgent(
    name="user_proxy",
    human_input_mode="NEVER",
    max_consecutive_auto_reply=1,
)

# --- Run the governed group chat --------------------------------------------

if __name__ == "__main__":
    from autogen_aumos.errors import GovernanceDeniedError

    print("Running governed group chat...")
    print("Trust levels: summary_agent=1, research_agent=2, data_agent=3")
    print()

    try:
        user_proxy.initiate_chat(
            manager,
            message=(
                "Research the latest developments in AI safety and store "
                "a summary in the database."
            ),
        )
    except GovernanceDeniedError as error:
        print()
        print(f"Governance denied: {error.subject}")
        print(f"Agent: {error.agent_name}")
        print(f"Reason: {error.reason}")
        print("The conversation was stopped by the governance policy.")
