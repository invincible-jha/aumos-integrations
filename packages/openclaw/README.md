# @aumos/openclaw-governance

Enterprise governance plugin for OpenClaw MCP servers.

Wraps any MCP server with a transparent JavaScript Proxy that enforces trust
and budget policies on every tool call, and records every decision to an
immutable audit trail — all without modifying the underlying server.

## Features

- Trust-level enforcement per MCP tool name (manual assignment only)
- Budget enforcement per tool call using static spending envelopes
- Immutable audit trail for every governance decision
- Zero-dependency integration — satisfies any MCP-compatible server interface
- Two denial modes: safe response (`message`) or exception (`error`)
- Pre-flight `check()` API for UI and orchestration layers

## Installation

```bash
npm install @aumos/openclaw-governance @aumos/governance
```

## Quick example

```typescript
import { createGovernanceEngine } from '@aumos/governance';
import { OpenClawGovernancePlugin } from '@aumos/openclaw-governance';

const engine = createGovernanceEngine({ agentId: 'my-agent' });

// Trust is always assigned manually by a human operator.
await engine.trust.setLevel('my-agent', 3, { assignedBy: 'ops-lead' });

const plugin = new OpenClawGovernancePlugin(engine, {
  agentId: 'my-agent',
  trustRequirements: { write_file: 3, delete_file: 5 },
  budgetCategories: { web_search: 'network' },
  onDenied: 'message',
});

const governed = plugin.wrap(myOpenClawServer);
const result = await governed.callTool('write_file', { path: '/tmp/out' });
```

## Documentation

- [Quickstart](docs/quickstart.md)
- [Configuration reference](docs/configuration.md)

## License

Apache-2.0. See [LICENSE](LICENSE).

---

Copyright (c) 2026 MuVeraAI Corporation
