# aumos-integrations Fire Line

This document defines the fire line for the aumos-integrations monorepo. Every contributor and every AI assistant MUST apply this boundary to every line of every file.

The fire line separates what AumOS governance describes (observable properties and decision outcomes) from what it explicitly excludes (implementation strategies, adaptive algorithms, and proprietary architecture).

---

## What Integration Packages May Contain

### Permitted

- **Governance checkpoints** — code that calls `engine.evaluate()` or `engine.evaluate_sync()` with a scope, agent ID, and optional amount, then acts on the returned `GovernanceDecision`.
- **Decision handling** — raise an exception on denial, skip a tool call, or log the outcome. These are the only three response modes.
- **Audit event recording** — call `engine.record_audit_event()` to log what happened. Recording only — no analysis.
- **Static configuration** — trust level requirements, budget category labels, and agent IDs set by the operator at initialization. Never computed at runtime.
- **Framework hook wiring** — attaching governance checkpoints to LangChain callbacks, LlamaIndex event handlers, CrewAI middleware, or equivalent framework extension points.
- **Public SDK types** — use types exported by `aumos-governance`. Do not define parallel types that shadow SDK types.

### Prohibited

- Trust score computation of any kind.
- Any logic that automatically changes a trust level based on runtime behavior.
- Budget allocation that uses runtime signals, history, or predictions.
- Anomaly detection, outlier identification, or pattern recognition on audit data.
- Any reference to or stub for a Forbidden Identifier (see below).
- Imports from any internal AumOS namespace (only `aumos-governance` is permitted).
- LangChain memory backend integration — that is PWM territory and is prohibited.
- Adaptive permission changes — governance rules are static per session.

---

## Forbidden Identifiers

These MUST NEVER appear in any source file in this repository.

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

The fire-line audit script (`scripts/fire-line-audit.sh`) enforces this automatically on every CI run.

---

## Additional Prohibitions

1. **No numeric performance targets** — no latency bounds, no throughput numbers, no timing assertions.
2. **No hardcoded numeric thresholds** — trust levels, budget amounts, and risk values are always operator-defined via configuration.
3. **No automatic trust progression** — trust level assignments are manual operations only.
4. **No predictive or ML-based logic** — integration packages are pure pass-through wrappers.

---

## Integration-Specific Extensions

Each package MUST provide its own `FIRE_LINE.md` that adds framework-specific rules on top of this monorepo baseline. See `packages/langchain/FIRE_LINE.md` as the reference example.

---

## Enforcement

1. **Authorship** — apply this checklist before opening any PR.
2. **Pre-push hook** — `scripts/fire-line-audit.sh` runs locally (configure with `git config core.hooksPath .githooks`).
3. **CI gate** — the audit job runs on every PR and blocks merge on any violation.

```bash
bash scripts/fire-line-audit.sh
```

---

## Evaluation Test

Before committing any line, ask:

> "Is this a governance CHECKPOINT (evaluate and act) or is this governance IMPLEMENTATION (compute, adapt, score)?"

Checkpoints are allowed. Implementation is not.

---

Copyright (c) 2026 MuVeraAI Corporation. Apache 2.0.
