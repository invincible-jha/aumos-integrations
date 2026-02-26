# Group Chat Governance in autogen-aumos

This document explains how `autogen-aumos` applies governance across an AutoGen
`GroupChat` where multiple agents with different trust levels participate in the
same conversation.

---

## Two Governance Layers

The integration provides governance at two granularities:

| Layer | Class | When it fires |
|-------|-------|---------------|
| Message layer | `MessageGuard` | Before each agent sends a message |
| Tool layer | `ToolGuard` | Before each function/tool is executed |

Both layers evaluate `engine.evaluate_sync()` and act on the returned
`GovernanceDecision`. The message layer is a coarse gate; the tool layer is a
fine-grained gate on function execution.

---

## Governing a Group Chat

Wrap each participant agent with `GovernedConversableAgent`. Use the inner
`.agent` attribute when constructing the `GroupChat`.

```python
from autogen import GroupChat, GroupChatManager
from autogen_aumos import GovernedConversableAgent

governed_researcher = GovernedConversableAgent(
    agent=research_agent,
    engine=engine,
    trust_level=2,
)
governed_writer = GovernedConversableAgent(
    agent=writer_agent,
    engine=engine,
    trust_level=1,
)

group_chat = GroupChat(
    agents=[governed_researcher.agent, governed_writer.agent],
    messages=[],
    max_round=6,
)
manager = GroupChatManager(groupchat=group_chat, llm_config=llm_config)
```

Each agent's trust level is set once, at construction, by the operator.

---

## Per-Agent Trust Levels

Different agents in the same group chat can hold different trust levels:

```python
# research_agent can access external APIs (trust level 2)
governed_researcher = GovernedConversableAgent(
    agent=research_agent, engine=engine, trust_level=2
)

# data_agent can write to the database (trust level 3)
governed_data = GovernedConversableAgent(
    agent=data_agent, engine=engine, trust_level=3
)

# summary_agent is read-only (trust level 1)
governed_summary = GovernedConversableAgent(
    agent=summary_agent, engine=engine, trust_level=1
)
```

The governance engine enforces the boundaries. This integration only passes the
trust level through at construction time.

---

## Per-Agent Scope Mapping

Configure different governance scopes for different agents' tool calls and
message sends:

```python
config = AutoGenGovernanceConfig(
    tool_scope_mapping={
        "web_search": "tool:web_access",
        "write_to_database": "tool:database_write",
        "summarise": "tool:summarise",
    },
    recipient_scope_mapping={
        "data_agent": "message:data_channel",
        "research_agent": "message:research_channel",
    },
)
```

All agents in the group chat can share the same `config` instance — each
evaluation passes the specific agent name and scope to the engine.

---

## Governing Message Routing

The `GroupChatManager` routes messages between agents. You can apply a
`MessageGuard` to govern the routing layer independently:

```python
from autogen_aumos import MessageGuard

routing_guard = MessageGuard(engine=engine, config=config)

# Check governance before the manager routes a message
result = routing_guard.check_message(
    sender_name="group_manager",
    recipient_name="data_agent",
    message="[routing decision]",
)
if not result.permitted:
    # Handle denied routing
    ...
```

---

## Denial Handling in Group Chats

Under `on_denied='raise'`, any governance denial stops the entire group chat
conversation. Handle `GovernanceDeniedError` at the `initiate_chat` call site:

```python
try:
    user_proxy.initiate_chat(manager, message="...")
except GovernanceDeniedError as error:
    print(f"Governance stopped the group chat: {error.reason}")
```

Under `on_denied='block'`, the blocked message is replaced with a denial notice
and the conversation continues. This can cause the group chat to behave
unexpectedly if the blocked message was load-bearing — use `'raise'` in
production unless you have a specific reason to use `'block'`.

---

## Audit Trail

Every message send and every function call result is recorded via
`engine.record_audit_event()` when `audit_all_actions=True` (the default).

The audit trail contains:
- The acting agent name.
- The subject (tool name or `'message'`).
- Whether the action succeeded or was denied.
- An optional output preview (truncated).

---

## Example

See [`examples/governed_group_chat.py`](../examples/governed_group_chat.py) for
a full example of a three-agent group chat where:

- `summary_agent` (trust level 1) can only summarise.
- `research_agent` (trust level 2) can search the web and summarise.
- `data_agent` (trust level 3) can write to the database.

---

Copyright (c) 2026 MuVeraAI Corporation. Apache 2.0.
