# langchain-aumos

Add AumOS governance to any LangChain agent in 3 lines.

```python
from langchain_aumos import AumOSGovernanceCallback

engine = GovernanceEngine(config)
callback = AumOSGovernanceCallback(engine)
agent = create_agent(llm, tools, callbacks=[callback])
```

Every tool call the agent makes is evaluated against your governance policy before execution. Denied calls raise `GovernanceDeniedError`, skip silently, or are logged — your choice.

---

## Installation

```bash
pip install langchain-aumos
```

Requires Python 3.10+, LangChain Core 0.2+, and aumos-governance 0.1+.

---

## What This Package Does

`langchain-aumos` wires AumOS governance checks into LangChain's callback system. When an agent attempts a tool call, the callback:

1. Identifies the tool name and infers a governance scope from it.
2. Calls `engine.evaluate_sync()` with the agent ID, scope, and optional spend amount.
3. If the decision is `ALLOW`, execution continues normally.
4. If the decision is `DENY`, the callback raises `GovernanceDeniedError`, returns a denial message, or logs the outcome — based on your `on_denied` setting.
5. After execution completes (or errors), the callback records an audit event.

---

## Core Components

### AumOSGovernanceCallback

Attach to any LangChain agent or chain via the `callbacks` parameter. Intercepts every tool call.

```python
from langchain_aumos import AumOSGovernanceCallback

callback = AumOSGovernanceCallback(
    engine=engine,
    agent_id="my-agent",
    on_denied="raise",   # 'raise' | 'skip' | 'log'
)
```

### GovernedTool

Wrap an individual tool with a governance gate. Useful when you want per-tool trust level requirements.

```python
from langchain_aumos import GovernedTool

governed = GovernedTool(
    tool=my_tool,
    engine=engine,
    required_trust_level=2,
    budget_category="api_calls",
)
```

### ChainGuard

Wrap a chain (not just individual tools) with a governance check at the chain entry point.

```python
from langchain_aumos import ChainGuard

guard = ChainGuard(engine=engine, trust_requirements={"my_chain": 1})
guarded_chain = guard.guard(my_chain)
```

---

## Configuration

```python
from langchain_aumos import GovernanceConfig

config = GovernanceConfig(
    agent_id="my-agent",
    on_denied="raise",
    default_scope="tool_call",
    audit_all_calls=True,
)
```

---

## Error Handling

```python
from langchain_aumos.errors import GovernanceDeniedError, ToolSkippedError

try:
    result = agent.invoke({"input": "..."})
except GovernanceDeniedError as error:
    print(f"Tool '{error.tool_name}' denied: {error.decision.reason}")
```

---

## Examples

- [`examples/quickstart.py`](examples/quickstart.py) — 3-line integration
- [`examples/governed_tools.py`](examples/governed_tools.py) — Per-tool governance gates
- [`examples/budget_controlled.py`](examples/budget_controlled.py) — Agent with spending limits

---

## Documentation

- [Quickstart](docs/quickstart.md)
- [Callback API](docs/callback-api.md)
- [Tool Wrapping](docs/tool-wrapping.md)

Full docs: [https://docs.aumos.ai/integrations/langchain](https://docs.aumos.ai/integrations/langchain)

---

## Fire Line

This package depends only on `langchain-core` and `aumos-governance`. It does not implement trust scoring, adaptive budgets, anomaly detection, memory backend integration, or any proprietary AumOS component. See [FIRE_LINE.md](FIRE_LINE.md).

---

## License

Apache 2.0. See [LICENSE](../../LICENSE).

Copyright (c) 2026 MuVeraAI Corporation
