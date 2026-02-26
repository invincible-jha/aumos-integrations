# Changelog

All notable changes to the aumos-integrations monorepo are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Per-package changelogs live alongside each package (e.g., `packages/langchain/CHANGELOG.md`).

---

## [Unreleased]

No unreleased changes at this time.

---

## [0.1.0] — 2026-02-26

### Added — Root Configuration

- `package.json` — monorepo workspace root
- `LICENSE` — Apache 2.0 (short notice, link to full text)
- `README.md` — Monorepo overview with package table and quick start
- `FIRE_LINE.md` — Monorepo-level fire line rules for all integrations
- `CLAUDE.md` — AI assistant instructions for the monorepo
- `CONTRIBUTING.md` — Contribution guide for new integrations and improvements
- `CHANGELOG.md` — This file
- `.gitignore` — Node.js, Python, and build artifact exclusions
- `scripts/fire-line-audit.sh` — Forbidden identifier audit script

### Added — langchain-aumos (packages/langchain v0.1.0)

See [packages/langchain/CHANGELOG.md](packages/langchain/CHANGELOG.md) for full details.

- `AumOSGovernanceCallback` — LangChain `BaseCallbackHandler` enforcing governance on tool calls
- `GovernedTool` — `BaseTool` wrapper adding a governance gate to any LangChain tool
- `ChainGuard` — Governance wrapper for LangChain chain execution
- `GovernanceConfig` — Integration configuration with Pydantic v2 validation
- `GovernanceDeniedError` and `ToolSkippedError` — Integration-specific exceptions
- Three runnable examples: quickstart, governed tools, budget-controlled agent
- API documentation: quickstart, callback API, tool wrapping

---

[Unreleased]: https://github.com/aumos-ai/aumos-integrations/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/aumos-ai/aumos-integrations/releases/tag/v0.1.0
