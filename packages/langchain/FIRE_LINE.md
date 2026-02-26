# langchain-aumos Fire Line

This document extends the [monorepo fire line](../../FIRE_LINE.md) with LangChain-specific constraints.

Read the monorepo fire line first. This document adds integration-specific rules on top.

---

## What This Package Does

`langchain-aumos` attaches AumOS governance checks to LangChain's callback and tool execution hooks. The package is a thin adapter — it translates LangChain events into governance evaluations and translates governance decisions back into LangChain behavior (allow, deny, log).

---

## LangChain-Specific Permitted Scope

This package MAY:

- Implement `BaseCallbackHandler` to intercept tool start, tool end, and tool error events.
- Implement `BaseTool` as a wrapper that adds a governance gate before delegating to an inner tool.
- Wrap chains with a pre-execution governance check.
- Read `serialized["name"]` from LangChain callback payloads to identify which tool is being called.
- Map tool names to governance scopes via a static, operator-provided mapping.
- Extract a numeric amount from tool inputs using a static, operator-provided field name.
- Call `engine.evaluate_sync()` and `engine.evaluate()` from `aumos-governance`.
- Call `engine.record_audit_event()` from `aumos-governance`.

---

## LangChain-Specific Prohibitions

This package MUST NOT:

- Integrate with LangChain memory backends, message stores, or chat history. Memory governance is a separate, out-of-scope concern.
- Modify LangChain agent state, tool lists, or prompt templates at runtime based on governance outcomes.
- Implement adaptive permission escalation — governance rules are static per engine configuration.
- Use LangChain's streaming APIs to inspect token-by-token output for governance decisions.
- Wrap LangChain's LLM call hooks (`on_llm_start`, `on_llm_end`) for governance enforcement — only tool calls are in scope.
- Store conversation history or produce summaries for any purpose.

---

## Dependency Constraint

This package's `pyproject.toml` dependencies MUST remain exactly:

```
langchain-core>=0.2.0
aumos-governance>=0.1.0
```

No other production dependencies. No LangChain memory packages. No LangChain community packages. No direct LLM provider SDKs.

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
