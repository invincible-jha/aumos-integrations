# CLAUDE.md — aumos-integrations Monorepo

This file provides instructions for AI assistants working anywhere in the aumos-integrations monorepo.

---

## Repository Identity

**aumos-integrations** is the monorepo for AumOS governance integrations with third-party AI frameworks.
GitHub org: `aumos-ai` | PyPI prefix: `langchain-aumos`, etc.

---

## Package Structure

```
aumos-integrations/
  packages/
    langchain/                  # langchain-aumos — Apache 2.0
      src/langchain_aumos/      # Python source
      examples/                 # Runnable usage examples
      docs/                     # Per-package API docs
  scripts/
    fire-line-audit.sh          # Forbidden identifier audit
```

---

## The Fire Line — Absolute Rule

**Read [FIRE_LINE.md](FIRE_LINE.md) before writing anything.**

These identifiers MUST NEVER appear in any source file:

```
progressLevel      promoteLevel       computeTrustScore  behavioralScore
adaptiveBudget     optimizeBudget     predictSpending
detectAnomaly      generateCounterfactual
PersonalWorldModel MissionAlignment   SocialTrust
CognitiveLoop      AttentionFilter    GOVERNANCE_PIPELINE
```

No adaptive algorithms. No behavioral scoring. No automatic trust progression.
No performance targets. No numeric thresholds.
Trust changes are MANUAL ONLY.
Budget allocations are STATIC ONLY.
Audit logging is RECORDING ONLY.

Run `bash scripts/fire-line-audit.sh` before every commit.

---

## Integration Contract

Every integration package in this monorepo MUST:

1. Depend ONLY on `aumos-governance` (the public SDK) and the target framework.
2. Never import from any proprietary AumOS namespace.
3. Implement governance as a CHECKPOINT at framework execution hooks — evaluate a `GovernanceDecision` and act on it (allow, deny, log). Nothing more.
4. Carry the SPDX license header on every source file.
5. Ship a `FIRE_LINE.md` that extends the monorepo fire line with integration-specific constraints.
6. Include `pyproject.toml` (Python) with `ruff`, `mypy`, and `pytest` dev dependencies.

---

## Code Standards

### Python
- Python 3.10+, type hints on every function signature
- Pydantic v2 for all models
- `ruff` linting, zero warnings
- `mypy --strict`, zero errors
- pytest, >80% coverage
- Every source file:
  ```python
  # SPDX-License-Identifier: Apache-2.0
  # Copyright (c) 2026 MuVeraAI Corporation
  ```

---

## Commit Convention

```
feat(langchain-aumos): description
fix(langchain-aumos): description
docs(langchain-aumos): description
test(langchain-aumos): description
chore(integrations): description
```

Commit messages explain WHY, not WHAT.

---

Copyright (c) 2026 MuVeraAI Corporation. Apache 2.0.
