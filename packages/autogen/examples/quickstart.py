# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Quickstart — add AumOS governance to an AutoGen agent in a few lines.

This example shows the minimal integration. ``GovernedConversableAgent`` wraps
an existing ``ConversableAgent`` and installs governance hooks on messages and
function calls at construction time.

Prerequisites:
    pip install autogen-aumos pyautogen aumos-governance

Usage:
    python examples/quickstart.py
"""

import autogen  # type: ignore[import]

# --- Define a simple function the agent can call ----------------------------

def get_current_date() -> str:
    """Return the current date as a string."""
    from datetime import date
    return str(date.today())


def calculate(expression: str) -> str:
    """
    Evaluate a safe mathematical expression.

    Args:
        expression: A mathematical expression string, e.g. '2 + 2'.
    """
    # Placeholder — replace with a safe evaluator in production.
    return f"Result of '{expression}': [computed]"


# --- Build the AutoGen agent as normal --------------------------------------

llm_config = {
    "config_list": [{"model": "gpt-4o-mini", "api_key": "YOUR_API_KEY"}],
    "functions": [
        {
            "name": "get_current_date",
            "description": "Return today's date.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "calculate",
            "description": "Evaluate a mathematical expression.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "The expression."}
                },
                "required": ["expression"],
            },
        },
    ],
}

assistant = autogen.ConversableAgent(
    name="assistant",
    system_message="You are a helpful assistant. Use your functions when appropriate.",
    llm_config=llm_config,
    function_map={
        "get_current_date": get_current_date,
        "calculate": calculate,
    },
)

user_proxy = autogen.UserProxyAgent(
    name="user_proxy",
    human_input_mode="NEVER",
    max_consecutive_auto_reply=3,
)

# --- The AumOS integration — wrap the assistant agent ----------------------

from aumos_governance import GovernanceEngine, GovernanceEngineConfig  # type: ignore[import]
from autogen_aumos import GovernedConversableAgent

engine = GovernanceEngine(GovernanceEngineConfig())

# Trust level 2 is assigned manually by the operator at construction time.
governed_assistant = GovernedConversableAgent(
    agent=assistant,
    engine=engine,
    trust_level=2,
)

# --- Run the conversation using the governed agent -------------------------

if __name__ == "__main__":
    from autogen_aumos.errors import GovernanceDeniedError

    try:
        # Use governed_assistant.agent in the AutoGen conversation.
        # The governance hooks are installed on the inner agent object.
        user_proxy.initiate_chat(
            governed_assistant.agent,
            message="What is today's date and what is 2 + 2?",
        )
    except GovernanceDeniedError as error:
        print(f"Governance denied: {error.subject}")
        print(f"Agent: {error.agent_name}")
        print(f"Reason: {error.reason}")
