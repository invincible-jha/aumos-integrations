# Tool Wrapping with GovernedTool

`GovernedTool` wraps any LangChain `BaseTool` with a per-tool governance gate.
Use it when different tools in your agent need different trust level requirements
or budget categories.

---

## Basic usage

```python
from langchain_aumos import GovernedTool

governed = GovernedTool(
    tool=my_tool,
    engine=engine,
    required_trust_level=2,
    budget_category="api_calls",
)
```

Pass `governed` to your agent exactly as you would pass `my_tool`. The
governance gate is transparent to the agent and to LangChain.

---

## govern() shorthand

```python
from langchain_aumos import govern

safe_tool = govern(my_tool, engine, required_trust_level=1)

# Wrap a list of tools at once
safe_tools = [govern(t, engine) for t in raw_tools]
```

---

## Constructor parameters

```python
GovernedTool(
    tool,
    engine,
    required_trust_level=0,
    budget_category=None,
    on_denied="raise",
    agent_id="default",
)
```

**tool** (`BaseTool`)
: The tool to wrap. Required.

**engine** (`GovernanceEngine`)
: An initialized `aumos-governance` engine. Required.

**required_trust_level** (`int`, default `0`)
: Minimum trust level the agent must hold. Passed to the engine as metadata;
  the engine enforces the requirement. Set to `0` to apply no trust level
  constraint.

**budget_category** (`str | None`, default `None`)
: Budget category label for this tool. When set, the engine can apply
  spending-envelope enforcement for this category. Set to `None` for tools
  that do not carry spend amounts.

**on_denied** (`"raise" | "skip" | "log"`, default `"raise"`)
: What to do when the governance engine returns a denial:
  - `"raise"` — raise `GovernanceDeniedError`.
  - `"skip"` — return a denial message string as the tool output; agent continues.
  - `"log"` — log the denial and allow execution.

**agent_id** (`str`, default `"default"`)
: Agent identifier for governance evaluations and audit records.

---

## Different trust levels per tool

```python
# Low-risk tool — trust level 1
safe_search = govern(web_search, engine, required_trust_level=1)

# High-risk tool — trust level 3, raise on denial
safe_exec = GovernedTool(
    tool=execute_code,
    engine=engine,
    required_trust_level=3,
    on_denied="raise",
)
```

---

## ChainGuard — chain-level governance

Use `ChainGuard` when you want a governance checkpoint at the chain entry point
rather than individual tool calls.

```python
from langchain_aumos import ChainGuard

guard = ChainGuard(
    engine=engine,
    agent_id="my-agent",
    on_denied="raise",
    trust_requirements={"summary_chain": 1, "analysis_chain": 2},
)

# Wrap a chain
safe_chain = guard.guard(my_chain, chain_name="summary_chain")

# Invoke it — governance runs before the chain receives input
result = safe_chain.invoke({"input": "..."})

# Or async
result = await safe_chain.ainvoke({"input": "..."})
```

`ChainGuard` and `AumOSGovernanceCallback` can be used together: the guard
checks governance at the chain boundary; the callback checks each tool call
within the chain.

---

## Combining GovernedTool and AumOSGovernanceCallback

You can use both at the same time. The callback provides a global gate for all
tool calls; `GovernedTool` adds per-tool requirements on top.

```python
from langchain_aumos import AumOSGovernanceCallback, govern

# Per-tool gates
safe_tools = [
    govern(search_tool, engine, required_trust_level=1),
    govern(exec_tool, engine, required_trust_level=3),
]

# Global callback as an additional layer
callback = AumOSGovernanceCallback(engine, agent_id="my-agent")

agent = create_agent(llm, safe_tools, callbacks=[callback])
```

---

## Async support

`GovernedTool` implements both `_run` (synchronous) and `_arun` (asynchronous).
No extra configuration is needed — LangChain selects the appropriate method.

---

## See also

- [`examples/governed_tools.py`](../examples/governed_tools.py) — runnable example
- [`examples/budget_controlled.py`](../examples/budget_controlled.py) — spending limits
- [Callback API reference](callback-api.md)
