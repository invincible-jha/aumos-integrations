# autogen-aumos Quickstart

Add AumOS governance to any AutoGen agent in a few lines.

---

## Installation

```bash
pip install autogen-aumos pyautogen aumos-governance
```

Requires Python 3.10+, pyautogen 0.2+, and aumos-governance 0.1+.

---

## The Minimal Integration

```python
from autogen import ConversableAgent
from aumos_governance import GovernanceEngine, GovernanceEngineConfig
from autogen_aumos import GovernedConversableAgent

# Your existing agent — unchanged
agent = ConversableAgent(name="assistant", ...)

# Wrap it with governance
engine = GovernanceEngine(GovernanceEngineConfig())
governed = GovernedConversableAgent(agent=agent, engine=engine, trust_level=2)

# Use governed.agent in your AutoGen conversation
user_proxy.initiate_chat(governed.agent, message="Hello")
```

`GovernedConversableAgent` installs governance hooks on the wrapped agent at
construction time. Your existing `ConversableAgent` definition is unchanged.

---

## What Happens at Runtime

1. At construction, `GovernedConversableAgent` sets the agent's trust level on
   the engine and registers reply and function hooks.
2. When the agent sends a message, the message governance hook calls
   `engine.evaluate_sync()` with the sender name and a scope derived from the
   recipient name.
3. When the agent executes a function, `governed_execute_function` calls
   `engine.evaluate_sync()` with the agent name and a scope derived from the
   function name.
4. On permit, execution continues normally and an audit event is recorded.
5. On denial, the integration raises `GovernanceDeniedError`, substitutes a
   block notice, or logs — based on `on_denied`.

---

## Handling Denials

```python
from autogen_aumos.errors import GovernanceDeniedError

try:
    user_proxy.initiate_chat(governed.agent, message="...")
except GovernanceDeniedError as error:
    print(f"Denied: {error.subject}")
    print(f"Agent: {error.agent_name}")
    print(f"Reason: {error.reason}")
```

The three denial modes:

| `on_denied` | Behaviour |
|-------------|-----------|
| `'raise'` (default) | Raise `GovernanceDeniedError`. The conversation fails. |
| `'block'` | Return a denial notice string in place of the message or function result. The conversation continues. |
| `'log'` | Log the denial and allow execution to proceed regardless. |

---

## Configuration

```python
from autogen_aumos.config import AutoGenGovernanceConfig
from autogen_aumos.types import DeniedAction

config = AutoGenGovernanceConfig(
    on_denied=DeniedAction.RAISE,
    tool_scope_mapping={
        "run_shell_command": "tool:shell",
        "query_database": "tool:database_read",
    },
    recipient_scope_mapping={
        "executor": "message:exec_channel",
    },
    govern_messages=True,
    govern_tools=True,
    audit_all_actions=True,
)

governed = GovernedConversableAgent(agent=agent, engine=engine, config=config)
```

---

## Trust Levels

Trust levels are assigned manually by the operator at construction time.
They are never computed from runtime behaviour.

```python
governed = GovernedConversableAgent(
    agent=agent,
    engine=engine,
    trust_level=3,  # Operator-assigned; static for the lifetime of this agent
)
```

---

## Standalone Guards

Use `MessageGuard` or `ToolGuard` independently when you need governance
checks outside a full `GovernedConversableAgent`:

```python
from autogen_aumos import MessageGuard, ToolGuard

message_guard = MessageGuard(engine=engine)
result = message_guard.check_message(
    sender_name="planner",
    recipient_name="executor",
    message="Please run the deployment.",
)

tool_guard = ToolGuard(engine=engine)
result = tool_guard.check_tool(
    agent_name="executor",
    tool_name="run_shell_command",
    args={"command": "ls -la"},
)
if not result.permitted:
    print(f"Blocked: {result.reason}")
```

---

## Examples

- [`examples/quickstart.py`](../examples/quickstart.py) — Minimal integration
- [`examples/governed_group_chat.py`](../examples/governed_group_chat.py) — Multi-agent group chat

---

## Next Steps

- [Group Chat Governance](group-chat-governance.md)
- Full docs: [https://docs.aumos.ai/integrations/autogen](https://docs.aumos.ai/integrations/autogen)

---

Copyright (c) 2026 MuVeraAI Corporation. Apache 2.0.
