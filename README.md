# aumos-integrations

Third-party framework integrations for the AumOS governance protocol suite.

Each package in this monorepo adds AumOS governance to a specific AI framework or library. All integrations depend only on `aumos-governance` (the public AumOS SDK) and the target framework — no proprietary AumOS internals.

---

## Packages

| Package | PyPI | Description |
|---|---|---|
| `packages/langchain` | [`langchain-aumos`](https://pypi.org/project/langchain-aumos/) | AumOS governance for LangChain agents |

---

## Quick Start

### LangChain

```bash
pip install langchain-aumos
```

```python
from langchain_aumos import AumOSGovernanceCallback

engine = GovernanceEngine(config)
callback = AumOSGovernanceCallback(engine)
agent = create_agent(llm, tools, callbacks=[callback])
```

That is the full integration — three lines.

---

## Adding a New Integration

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full process.

Short version:
1. Create `packages/<framework>/` following the structure in `packages/langchain/`.
2. Add your package path to the root `package.json` workspaces array (if it ships any JS tooling) or just add it as a peer directory for Python-only packages.
3. Ensure your package depends only on `aumos-governance` and the target framework. No proprietary AumOS imports.
4. Add a `FIRE_LINE.md` in your package root describing integration-specific constraints.
5. All source files must carry the SPDX header.
6. Pass `scripts/fire-line-audit.sh` before opening a PR.

---

## Fire Line

Read [FIRE_LINE.md](FIRE_LINE.md) before writing anything. The fire line rules govern what every integration in this monorepo may and may not implement.

Key rule: integrations add a governance checkpoint to framework execution hooks. They do not implement trust scoring, adaptive budgets, anomaly detection, or any proprietary AumOS component.

---

## Development

```bash
# Run fire line audit across all packages
bash scripts/fire-line-audit.sh

# Python — run from a package directory
cd packages/langchain
pip install -e ".[dev]"
ruff check src/
mypy src/
pytest
```

---

## License

Apache 2.0. See [LICENSE](LICENSE).

Copyright (c) 2026 MuVeraAI Corporation
