# Migrating from AutoGen to Microsoft Agent Framework with AumOS Governance

This guide covers migrating an existing AutoGen v0.2 deployment — already
integrated with `autogen-aumos` — to the Microsoft Agent Framework (MAF) while
retaining the same AumOS governance guarantees.

---

## Overview

Microsoft Agent Framework (MAF) is the successor to AutoGen. It introduces
`AgentChat` as the multi-agent collaboration surface and promotes a
middleware-first extensibility model in place of reply-function hooks.

`autogen-aumos` provides a governance bridge for both generations:

| Feature | AutoGen v0.2 | MAF / AgentChat |
|---------|--------------|-----------------|
| Agent base class | `ConversableAgent` | `ChatAgent` / `AssistantAgent` |
| Hook registration | `register_reply()` | Middleware via `add_middleware()` |
| Tool execution | `function_map` + hook | Tool schema + executor |
| Governance entry point | `GovernedConversableAgent` | `SemanticKernelGovernanceBridge` or `ConversationGovernor` |
| Trust assignment | Operator-set at construction | Operator-set at construction — unchanged |
| Audit log | `engine.record_audit_event()` | `ConversationAuditLog` |

The AumOS governance model is **unchanged**: trust levels are assigned manually
by the operator, budgets are static per-conversation envelopes, and the audit
log is a recording mechanism only.

---

## What Stays the Same

Before diving into the migration steps, note the invariants that carry forward:

- **Trust is manual.** You set `trust_level` on each agent at construction
  time. MAF does not automatically adjust trust based on conversation history.
- **Budgets are static envelopes.** You configure a maximum spend for a
  conversation. The `ConversationBudgetTracker` records cumulative usage
  against that ceiling — it does not resize the envelope at runtime.
- **Audit is append-only.** `ConversationAuditLog` records every governance
  decision. Nothing reads from the log to influence future decisions.
- **Denials require no special handling change.** The denial modes (`raise`,
  `block`, `log`) operate identically in MAF middleware.

---

## Step-by-Step Migration

### Step 1 — Update your dependencies

```toml
# pyproject.toml — before
dependencies = [
    "pyautogen>=0.2,<0.3",
    "autogen-aumos>=0.1",
    "aumos-governance>=0.1",
]

# pyproject.toml — after
dependencies = [
    "autogen-agentchat>=0.4",   # MAF AgentChat package
    "autogen-aumos>=0.2",        # Updated for MAF support
    "aumos-governance>=0.1",
]
```

### Step 2 — Replace `GovernedConversableAgent` with middleware

AutoGen v0.2 used reply-function hooks registered via `register_reply()`. MAF
uses a named middleware stack on each agent.

**Before (AutoGen v0.2):**

```python
from autogen import ConversableAgent
from autogen_aumos import GovernedConversableAgent

agent = ConversableAgent(name="planner", llm_config=llm_config)
governed = GovernedConversableAgent(agent=agent, engine=engine, trust_level=2)

# All conversation goes through governed.agent
user_proxy.initiate_chat(governed.agent, message="Start the workflow.")
```

**After (MAF):**

```python
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_aumos.conversation_governance import ConversationGovernor

agent = AssistantAgent(name="planner", model_client=model_client)

governor = ConversationGovernor(
    engine=engine,
    conversation_id="workflow-001",
    agent_trust_levels={"planner": 2, "executor": 3},
)

# Governor validates messages before they are processed
decision = governor.check_message(
    sender="user_proxy",
    recipient="planner",
    message="Start the workflow.",
)
if decision.permitted:
    await agent.on_messages([...], cancellation_token)
```

### Step 3 — Migrate tool governance

AutoGen v0.2 tools were intercepted by registering a function pre-execution
hook. MAF exposes tools as typed schemas executed by a tool executor. Wrap
your tool executor with `ConversationGovernor.check_tool_delegation()`.

**Before (AutoGen v0.2):**

```python
# Tool governance was automatic via GovernedConversableAgent
governed = GovernedConversableAgent(
    agent=agent,
    engine=engine,
    config=AutoGenGovernanceConfig(
        govern_tools=True,
        tool_scope_mapping={"run_query": "tool:database_read"},
    ),
)
```

**After (MAF):**

```python
from autogen_aumos.conversation_governance import ConversationGovernor

governor = ConversationGovernor(
    engine=engine,
    conversation_id="workflow-001",
    agent_trust_levels={"executor": 3},
)

# Before tool execution
decision = governor.check_tool_delegation(
    delegator="planner",
    delegate="executor",
    tool="run_query",
)
if not decision.permitted:
    raise GovernanceDeniedError(
        subject="run_query",
        agent_name="executor",
        reason=decision.reason,
    )

# Execute the tool
result = await run_query(params)
```

### Step 4 — Migrate Semantic Kernel planner governance

If your AutoGen v0.2 deployment used a Semantic Kernel planner alongside
AutoGen agents, migrate to `SemanticKernelGovernanceBridge`.

**Before (AutoGen v0.2 + SK):**

```python
# SK kernel was not governed — calls bypassed AumOS
kernel = Kernel()
kernel.add_plugin(my_plugin, plugin_name="data")
result = await kernel.invoke("data", "fetch_records", query=query_params)
```

**After (MAF + SK bridge):**

```python
from autogen_aumos.semantic_kernel_bridge import (
    GovernedKernelPlugin,
    SemanticKernelGovernanceBridge,
)

bridge = SemanticKernelGovernanceBridge(engine=engine, trust_level=2)

governed_plugin = GovernedKernelPlugin(
    plugin=my_plugin,
    plugin_name="data",
    bridge=bridge,
)

# Every function call through the plugin is governance-checked
result = await governed_plugin.invoke("fetch_records", query=query_params)
```

### Step 5 — Migrate the audit log wiring

AutoGen v0.2 audit events were written via `engine.record_audit_event()` inside
the guard classes. In the MAF integration, `ConversationAuditLog` collects
governance decisions for the whole conversation in one place.

**Before (AutoGen v0.2):**

```python
# Audit was implicit — engine.record_audit_event() was called inside MessageGuard
# To query the log you accessed the engine directly
events = engine.get_audit_events(agent_name="planner")
```

**After (MAF):**

```python
from autogen_aumos.conversation_governance import ConversationGovernor

governor = ConversationGovernor(engine=engine, conversation_id="wf-001")
# ... run conversation ...

log = governor.audit_log.get_entries()
for entry in log:
    print(entry.sender, entry.recipient, entry.permitted, entry.reason)
```

---

## Governance Configuration Migration

The `AutoGenGovernanceConfig` configuration model carries forward with minimal
changes. The MAF integration reads the same fields; the only difference is where
the config is passed.

| AutoGen v0.2 | MAF |
|--------------|-----|
| `AutoGenGovernanceConfig(on_denied=...)` passed to `GovernedConversableAgent` | Same config passed to `ConversationGovernor` |
| `tool_scope_mapping` | Unchanged — passed to `ConversationGovernor` |
| `recipient_scope_mapping` | Renamed to `agent_scope_mapping` in `ConversationGovernor` |
| `govern_messages=True` | `govern_messages=True` on `ConversationGovernor` |
| `govern_tools=True` | Enforced via `check_tool_delegation()` |
| `audit_all_actions=True` | `ConversationAuditLog` always records — controlled by `record_permitted` flag |

---

## Trust Level Mapping Between AutoGen Roles and MAF Capabilities

AutoGen v0.2 roles (`USER_PROXY`, `ASSISTANT`, `EXECUTOR`) map to MAF
capability descriptors. Use this table when setting trust levels on
`ConversationGovernor`.

| AutoGen v0.2 role | Typical trust level | MAF agent type | Notes |
|-------------------|---------------------|----------------|-------|
| `UserProxyAgent` (no tools) | 1 | `UserProxyAgent` | Read-only proxy |
| `UserProxyAgent` (code exec) | 3 | `CodeExecutorAgent` | Can run code |
| `AssistantAgent` (no tools) | 1–2 | `AssistantAgent` | LLM-only |
| `AssistantAgent` (with tools) | 2–3 | `AssistantAgent` + tool schema | Tool access |
| `GroupChatManager` | 2 | `SelectorGroupChat` manager | Routing only |
| Custom execution agent | 3–4 | `AssistantAgent` (executor) | Execution access |

Trust levels remain integers in [0, 5]. The table shows typical mappings;
operators should assign levels based on their own threat model.

---

## Testing the Migration

### Verify governance still fires

```python
import pytest
from unittest.mock import AsyncMock
from autogen_aumos.conversation_governance import ConversationGovernor

@pytest.mark.asyncio
async def test_message_governance_blocks_untrusted_sender() -> None:
    engine = AsyncMock()
    engine.evaluate.return_value = type("D", (), {"permitted": False, "reason": "denied"})()

    governor = ConversationGovernor(
        engine=engine,
        conversation_id="test-001",
        agent_trust_levels={"low_trust_agent": 1},
    )

    result = governor.check_message(
        sender="low_trust_agent",
        recipient="executor",
        message="Run the deployment script.",
    )
    assert not result.permitted
```

### Verify audit log records decisions

```python
def test_audit_log_records_all_checks() -> None:
    governor = ConversationGovernor(
        engine=engine,
        conversation_id="test-002",
        agent_trust_levels={"agent_a": 2},
    )
    governor.check_message("agent_a", "agent_b", "Hello")
    governor.check_message("agent_a", "agent_b", "World")

    entries = governor.audit_log.get_entries()
    assert len(entries) == 2
```

### Verify budget ceiling is respected

```python
def test_budget_ceiling_blocks_over_limit() -> None:
    governor = ConversationGovernor(
        engine=engine,
        conversation_id="test-003",
        agent_trust_levels={"agent_a": 3},
        conversation_budget=10.0,
    )
    governor.budget_tracker.record_spend(9.0)
    result = governor.check_spend(amount=2.0, agent_name="agent_a")
    assert not result.permitted
    assert "budget" in result.reason
```

---

## Rollback Plan

If the MAF migration causes issues, you can run both integration versions in
parallel during a transition period. `GovernedConversableAgent` continues to
work with AutoGen v0.2 agents. Point new agents at the MAF middleware while
legacy agents continue using reply hooks.

---

Copyright (c) 2026 MuVeraAI Corporation. Apache 2.0.
