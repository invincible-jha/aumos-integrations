# langchain-aumos Quickstart

Add AumOS governance to a LangChain agent in 3 lines.

---

## Installation

```bash
pip install langchain-aumos
```

Requires Python 3.10+, LangChain Core 0.2+, and aumos-governance 0.1+.

---

## The 3-line integration

```python
from aumos_governance import GovernanceEngine, GovernanceEngineConfig
from langchain_aumos import AumOSGovernanceCallback

engine = GovernanceEngine(GovernanceEngineConfig(agent_id="my-agent"))
callback = AumOSGovernanceCallback(engine)
agent = create_agent(llm, tools, callbacks=[callback])
```

That is the complete integration. Every tool call the agent attempts is
evaluated against your governance policy before execution proceeds.

---

## What happens on a denied tool call

By default (``on_denied='raise'``), a denied tool call raises
``GovernanceDeniedError`` and stops the agent run:

```python
from langchain_aumos.errors import GovernanceDeniedError

try:
    result = agent.invoke({"input": "..."})
except GovernanceDeniedError as error:
    print(f"Tool '{error.tool_name}' denied: {error.reason}")
```

To silently skip denied tools instead of stopping:

```python
callback = AumOSGovernanceCallback(engine, on_denied="skip")
```

To log and continue regardless:

```python
callback = AumOSGovernanceCallback(engine, on_denied="log")
```

---

## Configuring via GovernanceConfig

For more control, pass a ``GovernanceConfig`` object:

```python
from langchain_aumos import AumOSGovernanceCallback, GovernanceConfig

config = GovernanceConfig(
    agent_id="my-agent",
    on_denied="raise",
    default_scope="tool_call",
    scope_mapping={"web_search": "external_api", "calculator": "compute"},
    audit_all_calls=True,
)

callback = AumOSGovernanceCallback(engine, config=config)
```

---

## Full example

See [`examples/quickstart.py`](../examples/quickstart.py) for a runnable
end-to-end example with a LangChain OpenAI agent.

---

## Next steps

- [Callback API reference](callback-api.md) — full parameter documentation
- [Tool wrapping](tool-wrapping.md) — per-tool governance requirements
- `examples/governed_tools.py` — different trust levels per tool
- `examples/budget_controlled.py` — enforce spending limits
