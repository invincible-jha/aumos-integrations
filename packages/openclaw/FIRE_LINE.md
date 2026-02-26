# Fire Line — @aumos/openclaw-governance

This document defines the absolute boundary between open-source plugin code
and proprietary AumOS platform code. Read before writing any source file.

## Dependency Constraint

This package depends ONLY on:
- `@aumos/governance` (the public SDK — BSL 1.1)
- `zod` (runtime validation)

It MUST NOT import from any proprietary AumOS namespace or access OpenClaw
internals beyond the `MCPServer.callTool()` interface.

## Forbidden Identifiers

These identifiers MUST NEVER appear in any source file in this package:

```
progressLevel      promoteLevel       computeTrustScore  behavioralScore
adaptiveBudget     optimizeBudget     predictSpending
detectAnomaly      generateCounterfactual
PersonalWorldModel MissionAlignment   SocialTrust
CognitiveLoop      AttentionFilter    GOVERNANCE_PIPELINE
```

## Plugin-Specific Rules

### Trust
- ALLOWED: `engine.trust.checkLevel()`, `engine.trust.getLevel()`
- FORBIDDEN: Any method that modifies trust levels from within the plugin
- Trust levels are set MANUALLY by human operators outside this plugin

### Budget
- ALLOWED: `engine.budget.checkBudget()`, `engine.budget.recordSpending()`
- FORBIDDEN: Any adaptive or predictive budget method
- Budget limits are STATIC — set at envelope creation, never adjusted here

### Audit
- ALLOWED: `engine.audit.log()` — record decisions only
- FORBIDDEN: Reading audit records, pattern analysis, anomaly detection

### MCP Interface
- ALLOWED: Intercepting `callTool` via Proxy
- FORBIDDEN: Accessing any OpenClaw internal state beyond the tool call result

## What This Plugin Is

A governance CHECKPOINT. It evaluates a GovernanceDecision and acts on it
(allow, deny, log). Nothing more.

## Enforcement

Run `bash scripts/fire-line-audit.sh` from the monorepo root before every commit.

---

Copyright (c) 2026 MuVeraAI Corporation. Apache 2.0.
