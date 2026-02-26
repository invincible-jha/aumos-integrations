# Multi-Agent Governance in crewai-aumos

This document explains how `crewai-aumos` applies governance across a multi-agent
CrewAI crew where different agents require different levels of access.

---

## Two Governance Layers

The integration provides governance at two granularities:

| Layer | Class | When it fires |
|-------|-------|---------------|
| Task level | `TaskGuard` | Before each task is dispatched to its agent |
| Tool level | `GovernedCrewTool` | Before each tool call within a task |

Both layers evaluate `engine.evaluate_sync()` and act on the returned
`GovernanceDecision`. The task layer is a coarse gate; the tool layer is a
fine-grained gate.

---

## Per-Agent Trust Levels

Each agent role can be assigned a trust level. These are set once, at crew
construction, by the operator. They are never modified based on runtime
behaviour.

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

When `GovernedCrew` constructs, it calls `engine.trust.set_level(role, level)`
for each configured agent. Enforcement of what each level permits is the
responsibility of the governance engine, not this integration.

---

## Per-Agent Scope Mapping

You can configure different governance scopes for task-level checks depending
on which agent is executing:

```python
config = CrewGovernanceConfig(
    agent_task_scope_mapping={
        "junior_researcher": "task:restricted",
        "senior_analyst": "task:standard",
        "compliance_officer": "task:privileged",
    },
)
```

And for tool calls, you can map individual tool names to specific scopes:

```python
config = CrewGovernanceConfig(
    tool_scope_mapping={
        "read_public_data": "data_access:public",
        "read_internal_data": "data_access:internal",
        "write_records": "data_write:internal",
    },
)
```

The governance engine receives the scope string and applies its policy. The
integration only passes the scope — it does not implement policy logic.

---

## Denial Handling Across Agents

The `on_denied` setting in `CrewGovernanceConfig` applies uniformly to all
agents in the crew. The three modes:

**`raise` (default)** — Stop the entire crew run.

```python
config = CrewGovernanceConfig(on_denied="raise")
```

Use this when a governance denial is a hard error that must not be silently
skipped. The calling code must handle `GovernanceDeniedError`.

**`skip`** — Return a denial message as the tool output and continue.

```python
config = CrewGovernanceConfig(on_denied="skip")
```

The agent receives the denial message as if it were a tool response. The crew
continues to the next task or tool call. Use this for soft enforcement where
partial results are acceptable.

**`log`** — Log the denial and allow execution to proceed.

```python
config = CrewGovernanceConfig(on_denied="log")
```

Governance denials are recorded in the audit trail but do not affect execution.
Use this for monitoring or gradual rollout.

---

## Audit Trail

Every tool call result — both allowed and denied — is recorded via
`engine.record_audit_event()` when `audit_all_calls=True` (the default).

```python
config = CrewGovernanceConfig(
    audit_all_calls=True,
    audit_output_preview_length=256,  # characters of output captured
)
```

Set `audit_output_preview_length=0` to omit output previews from audit records.

---

## Example: Hierarchical Crew

See [`examples/hierarchical_trust.py`](../examples/hierarchical_trust.py) for
a full example of a three-tier crew where:

- `junior_researcher` (trust level 1) can only access public data.
- `senior_analyst` (trust level 2) can access internal data.
- `compliance_officer` (trust level 3) can write records and read audit logs.

The trust levels are assigned manually by the operator. The governance engine
enforces the boundaries.

---

## Using TaskGuard Directly

When you need task-level governance outside a full `GovernedCrew`:

```python
from crewai_aumos import TaskGuard

guard = TaskGuard(engine=engine)
result = guard.guard_task(task, agent_role="researcher")

if result.permitted:
    crew.kickoff()
else:
    print(f"Task blocked: {result.reason}")
```

`guard_task` returns a `GuardResult` with `permitted`, `reason`, `scope`, and
`agent_role` fields. When `on_denied='raise'`, it raises `GovernanceDeniedError`
instead of returning a result with `permitted=False`.

---

Copyright (c) 2026 MuVeraAI Corporation. Apache 2.0.
