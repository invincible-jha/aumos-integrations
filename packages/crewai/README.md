# crewai-aumos

Add AumOS governance to any CrewAI crew in a few lines.

```python
from crewai import Crew
from aumos_governance import GovernanceEngine, GovernanceEngineConfig
from crewai_aumos import GovernedCrew

engine = GovernanceEngine(GovernanceEngineConfig())
governed = GovernedCrew(crew=crew, engine=engine)
result = governed.kickoff(inputs={"topic": "AI safety"})
```

Every tool call every agent makes is evaluated against your governance policy
before execution. Denied calls raise `GovernanceDeniedError`, skip with a
message, or are logged — your choice.

---

## Installation

```bash
pip install crewai-aumos
```

Requires Python 3.10+, CrewAI 0.30+, and aumos-governance 0.1+.

---

## What This Package Does

`crewai-aumos` wraps a CrewAI `Crew` with two governance layers:

1. **Task layer** — evaluated before each task is dispatched to its agent.
   Uses `TaskGuard` to call `engine.evaluate_sync()` with the task scope and
   agent role. Denied tasks either stop the crew, return a skip message, or are
   logged.

2. **Tool layer** — evaluated before each tool call within a task. Uses
   `GovernedCrewTool` to intercept every `run()` call, evaluate governance, and
   either allow or deny execution.

Both layers call `engine.record_audit_event()` after each execution to maintain
an audit trail.

---

## Core Components

### GovernedCrew

The top-level entry point. Wraps an existing `Crew` at construction time.

```python
from crewai_aumos import GovernedCrew

governed = GovernedCrew(
    crew=crew,
    engine=engine,
    agent_trust_levels={
        "researcher": 2,
        "writer": 1,
    },
)
result = governed.kickoff()
```

### GovernedCrewTool

Wraps a single CrewAI tool with a governance gate. Useful when you need
per-tool trust level requirements.

```python
from crewai_aumos import GovernedCrewTool

governed_tool = GovernedCrewTool(
    tool=search_tool,
    engine=engine,
    agent_role="researcher",
    required_trust_level=2,
    budget_category="web_search",
)
```

### wrap_tools

Convenience function to wrap a list of tools at once.

```python
from crewai_aumos import wrap_tools

governed_tools = wrap_tools(raw_tools, engine, agent_role="analyst")
```

### TaskGuard

Standalone task-level governance. Use this when you need task checkpoints
without a full `GovernedCrew`.

```python
from crewai_aumos import TaskGuard

guard = TaskGuard(engine=engine)
result = guard.guard_task(task, agent_role="researcher")
if not result.permitted:
    print(f"Blocked: {result.reason}")
```

---

## Configuration

```python
from crewai_aumos.config import CrewGovernanceConfig
from crewai_aumos.types import DeniedAction

config = CrewGovernanceConfig(
    on_denied=DeniedAction.RAISE,
    tool_scope_mapping={
        "web_search": "search_scope",
        "database_query": "data_scope",
    },
    agent_task_scope_mapping={
        "researcher": "task:standard",
        "analyst": "task:privileged",
    },
    amount_field="amount",
    audit_all_calls=True,
)
```

---

## Trust Levels

Trust levels are assigned manually by the operator at construction time.
They are never computed from runtime behaviour.

```python
governed = GovernedCrew(
    crew=crew,
    engine=engine,
    agent_trust_levels={
        "junior_researcher": 1,
        "senior_analyst": 2,
        "compliance_officer": 3,
    },
)
```

---

## Error Handling

```python
from crewai_aumos.errors import GovernanceDeniedError

try:
    result = governed.kickoff()
except GovernanceDeniedError as error:
    print(f"Subject: {error.subject}")
    print(f"Agent role: {error.agent_role}")
    print(f"Reason: {error.reason}")
```

---

## Examples

- [`examples/quickstart.py`](examples/quickstart.py) — Minimal integration
- [`examples/multi_agent_budget.py`](examples/multi_agent_budget.py) — Per-agent spending limits
- [`examples/hierarchical_trust.py`](examples/hierarchical_trust.py) — Multi-tier trust levels

---

## Documentation

- [Quickstart](docs/quickstart.md)
- [Multi-Agent Governance](docs/multi-agent-governance.md)

Full docs: [https://docs.aumos.ai/integrations/crewai](https://docs.aumos.ai/integrations/crewai)

---

## Fire Line

This package depends only on `crewai` (peer) and `aumos-governance`. It does
not implement trust scoring, adaptive budgets, anomaly detection, memory backend
integration, or any proprietary AumOS component. See [FIRE_LINE.md](FIRE_LINE.md).

---

## License

Apache 2.0. See [LICENSE](../../LICENSE).

Copyright (c) 2026 MuVeraAI Corporation
