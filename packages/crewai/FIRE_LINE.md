# crewai-aumos Fire Line

This document extends the [monorepo fire line](../../FIRE_LINE.md) with
CrewAI-specific constraints.

Read the monorepo fire line first. This document adds integration-specific
rules on top.

---

## What This Package Does

`crewai-aumos` attaches AumOS governance checkpoints to CrewAI agent tool calls
and task dispatch. The package is a thin adapter — it wraps existing CrewAI
objects at construction time and translates governance decisions back into
CrewAI behaviour (allow, deny, log).

---

## CrewAI-Specific Permitted Scope

This package MAY:

- Wrap any CrewAI-compatible tool object with a `GovernedCrewTool` that calls
  `engine.evaluate_sync()` before delegating to the inner tool's `run` method.
- Wrap a `Crew` object with `GovernedCrew` to install governed tool wrappers
  on every agent and evaluate `TaskGuard` checkpoints before `kickoff`.
- Read `agent.role`, `agent.tools`, `task.agent`, and `task.description` from
  CrewAI objects to build governance evaluation context.
- Map agent role strings to governance scopes via a static, operator-provided
  `agent_task_scope_mapping`.
- Map tool names to governance scopes via a static, operator-provided
  `tool_scope_mapping`.
- Set agent trust levels via `engine.trust.set_level(role, level)` at
  construction time. This is a one-time, operator-initiated assignment.
- Call `engine.evaluate_sync()` and `engine.record_audit_event()` from
  `aumos-governance`.

---

## CrewAI-Specific Prohibitions

This package MUST NOT:

- Integrate with CrewAI's memory, knowledge base, or long-term storage backends.
  Memory governance is out of scope.
- Modify a task's `description`, `expected_output`, or `agent` assignment based
  on a governance outcome. Governance changes execution flow, not task content.
- Implement inter-agent trust negotiation. An agent cannot grant or receive
  trust from another agent at runtime.
- Use CrewAI's process-level hooks (e.g., `Process.hierarchical` manager agent
  callbacks) for governance enforcement — governance wraps tools and tasks only.
- Implement automatic escalation of agent trust levels under any condition.
  Trust level changes are manual-only operations performed at construction.

---

## Dependency Constraint

This package's `pyproject.toml` production dependencies MUST remain exactly:

```
aumos-governance>=0.1.0
```

`crewai>=0.30` is a peer dependency listed under `[project.optional-dependencies]`.
No other production dependencies. No CrewAI memory packages. No LLM provider SDKs.

---

## Forbidden Identifiers (Inherited + Reiterated)

These MUST NEVER appear in any `.py`, `.md`, or `.toml` file in this package:

```
progressLevel
promoteLevel
computeTrustScore
behavioralScore
adaptiveBudget
optimizeBudget
predictSpending
detectAnomaly
generateCounterfactual
PersonalWorldModel
MissionAlignment
SocialTrust
CognitiveLoop
AttentionFilter
GOVERNANCE_PIPELINE
```

---

## Enforcement

Run from the monorepo root:

```bash
bash scripts/fire-line-audit.sh
```

Or from this package directory:

```bash
bash ../../scripts/fire-line-audit.sh
```

---

Copyright (c) 2026 MuVeraAI Corporation. Apache 2.0.
