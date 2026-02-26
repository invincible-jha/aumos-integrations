# Contributing to aumos-integrations

Thank you for your interest in contributing an AumOS governance integration.

---

## Before You Start

1. Read [FIRE_LINE.md](FIRE_LINE.md) — this is non-negotiable. Every contribution must comply.
2. Check whether your target framework already has a package under `packages/`. If so, open an issue describing your improvement before writing code.
3. New framework integrations must be discussed in an issue first so scope and fire line rules can be agreed upon before implementation begins.

---

## Contribution Types

### Bug fixes and improvements to existing packages

1. Fork the repository and create a branch: `fix/langchain-aumos-description`.
2. Make your change. Keep it focused — one logical change per PR.
3. Run the full verification suite from the package directory:
   ```bash
   ruff check src/
   mypy src/
   pytest
   bash ../../scripts/fire-line-audit.sh
   ```
4. Open a PR with a description explaining why the change is needed.

### New framework integration

1. Open an issue titled `feat: <framework-name> integration` and describe:
   - What framework hooks you plan to use.
   - The dependency chain (framework + `aumos-governance` only).
   - Any integration-specific fire line rules you will add.
2. After discussion, create a branch: `feature/langchain-aumos-description`.
3. Use `packages/langchain/` as the structural reference.
4. Your package MUST include:
   - `pyproject.toml` (or equivalent) with `ruff`, `mypy`, `pytest` dev dependencies.
   - `FIRE_LINE.md` extending the monorepo baseline.
   - `src/<package_name>/` with SPDX headers on every file.
   - `examples/` with at least one runnable quickstart.
   - `docs/` with a quickstart guide.
5. Add your package to the root `README.md` packages table.
6. Open a PR.

### Documentation improvements

Documentation PRs follow the same branch naming (`docs/description`) and require fire-line-audit to pass.

---

## Code Standards

- Python 3.10+, type hints on every function signature.
- `ruff` — zero warnings.
- `mypy --strict` — zero errors.
- pytest — >80% coverage.
- Every source file carries the SPDX header:
  ```python
  # SPDX-License-Identifier: Apache-2.0
  # Copyright (c) 2026 MuVeraAI Corporation
  ```

---

## Commit Convention

```
feat(package-name): why this matters
fix(package-name): why this was broken
docs(package-name): what was missing or wrong
test(package-name): what gap this closes
chore(integrations): what maintenance this performs
```

Commit messages explain WHY, not WHAT.

---

## Pull Request Checklist

- [ ] Fire line audit passes (`bash scripts/fire-line-audit.sh`)
- [ ] `ruff check` passes with zero warnings
- [ ] `mypy --strict` passes with zero errors
- [ ] `pytest` passes with >80% coverage
- [ ] SPDX headers present on all new source files
- [ ] `FIRE_LINE.md` updated if new constraints apply
- [ ] `CHANGELOG.md` entry added under `[Unreleased]`

---

## License

By contributing, you agree that your contribution is licensed under Apache 2.0.

---

Copyright (c) 2026 MuVeraAI Corporation. Apache 2.0.
