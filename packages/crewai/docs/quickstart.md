# crewai-aumos Quickstart

Add AumOS governance to any CrewAI crew in a few lines.

---

## Installation

```bash
pip install crewai-aumos crewai aumos-governance
```

Requires Python 3.10+, CrewAI 0.30+, and aumos-governance 0.1+.

---

## The Minimal Integration

```python
from crewai import Crew, Agent, Task
from aumos_governance import GovernanceEngine, GovernanceEngineConfig
from crewai_aumos import GovernedCrew

# Your existing crew — unchanged
crew = Crew(agents=[researcher, writer], tasks=[research_task, write_task])

# Wrap it with governance
engine = GovernanceEngine(GovernanceEngineConfig())
governed = GovernedCrew(crew=crew, engine=engine)

# Run as normal
result = governed.kickoff(inputs={"topic": "AI safety"})
```

`GovernedCrew` replaces each agent's tools with governed wrappers and evaluates
task-level checkpoints before `kickoff` proceeds. Your existing `Crew`
definition is unchanged.

---

## What Happens at Runtime

1. At construction, `GovernedCrew` wraps every tool in every agent's tool list
   with a `GovernedCrewTool` instance.
2. When `kickoff` is called, task-level governance checkpoints are evaluated
   for each task in definition order before the crew begins.
3. As each agent executes, every tool call is evaluated against the governance
   engine before the tool runs.
4. On permit, the tool executes normally and an audit event is recorded.
5. On denial, the integration raises `GovernanceDeniedError`, returns a skip
   message, or logs — based on your `on_denied` setting.

---

## Handling Denials

```python
from crewai_aumos.errors import GovernanceDeniedError

try:
    result = governed.kickoff()
except GovernanceDeniedError as error:
    print(f"Denied: {error.subject}")
    print(f"Agent role: {error.agent_role}")
    print(f"Reason: {error.reason}")
```

The three denial modes:

| `on_denied` | Behaviour |
|-------------|-----------|
| `'raise'` (default) | Raise `GovernanceDeniedError`. The crew run fails. |
| `'skip'` | Return a denial message string as the tool output. The crew continues. |
| `'log'` | Log the denial and allow execution to proceed regardless. |

---

## Configuration

```python
from crewai_aumos.config import CrewGovernanceConfig
from crewai_aumos.types import DeniedAction

config = CrewGovernanceConfig(
    on_denied=DeniedAction.RAISE,
    default_tool_scope="crew_tool_call",
    tool_scope_mapping={
        "web_search": "search_scope",
        "database_query": "data_scope",
    },
    audit_all_calls=True,
)

governed = GovernedCrew(crew=crew, engine=engine, config=config)
```

---

## Trust Levels

Trust levels are assigned manually at construction time. They are never
computed from runtime behaviour.

```python
governed = GovernedCrew(
    crew=crew,
    engine=engine,
    agent_trust_levels={
        "researcher": 2,
        "writer": 1,
    },
)
```

---

## Governing Individual Tools

When you need per-tool governance configuration without wrapping a full crew:

```python
from crewai_aumos import GovernedCrewTool, wrap_tools

# Wrap a single tool
governed_tool = GovernedCrewTool(
    tool=search_tool,
    engine=engine,
    agent_role="researcher",
    required_trust_level=1,
    budget_category="web_search",
)

# Or wrap a list of tools at once
governed_tools = wrap_tools(raw_tools, engine, agent_role="researcher")
```

---

## Examples

- [`examples/quickstart.py`](../examples/quickstart.py) — Minimal integration
- [`examples/multi_agent_budget.py`](../examples/multi_agent_budget.py) — Per-agent budget envelopes
- [`examples/hierarchical_trust.py`](../examples/hierarchical_trust.py) — Multi-tier trust

---

## Next Steps

- [Multi-Agent Governance](multi-agent-governance.md)
- Full docs: [https://docs.aumos.ai/integrations/crewai](https://docs.aumos.ai/integrations/crewai)

---

Copyright (c) 2026 MuVeraAI Corporation. Apache 2.0.
