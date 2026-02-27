# Universal MCP Client Guide — OpenClaw Governance Plugin

Add AumOS governance to any MCP-compatible AI client using the
`@aumos/openclaw-governance` plugin. This guide covers configuration for the
most common MCP clients and a generic setup path for everything else.

---

## What OpenClaw Does

`@aumos/openclaw-governance` wraps any MCP server with a governance proxy that
evaluates two gates before every tool call:

1. **Trust gate** — the calling agent must hold at least the configured trust
   level for the requested tool. Trust levels are set manually by an operator;
   they are never derived from runtime behaviour.
2. **Budget gate** — the relevant spending envelope must have remaining capacity.
   Budgets are static limits set at configuration time.

Every decision — permit or deny — is written to the audit trail. Audit recording
is append-only; the plugin never reads back or analyses audit entries.

---

## Installation

```bash
npm install @aumos/openclaw-governance @aumos/governance
```

Requires Node.js 18+ and an MCP client that supports external MCP server
configuration via a JSON config file.

---

## Claude Desktop

Claude Desktop reads its MCP server list from `claude_desktop_config.json`.

**File location:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

**Minimal configuration:**

```json
{
  "mcpServers": {
    "governed-filesystem": {
      "command": "node",
      "args": [
        "/path/to/your/governed-server-entry.js"
      ],
      "env": {
        "AUMOS_AGENT_ID": "claude-desktop-user"
      }
    }
  }
}
```

**governed-server-entry.js** (create this file alongside your config):

```js
import { createServer } from '@modelcontextprotocol/sdk/server/stdio.js';
import { OpenClawGovernancePlugin } from '@aumos/openclaw-governance';
import { GovernanceEngine, GovernanceEngineConfig } from '@aumos/governance';
import { createFilesystemServer } from '@modelcontextprotocol/server-filesystem';

const engine = new GovernanceEngine(new GovernanceEngineConfig());

const plugin = new OpenClawGovernancePlugin({
  agentId: process.env.AUMOS_AGENT_ID ?? 'claude-desktop',
  trustRequirements: {
    write_file: 2,
    delete_file: 3,
    read_file: 1,
  },
  budgetCategories: {
    web_search: 'search_budget',
  },
  onDenied: 'message',
});

const rawServer = createFilesystemServer({ allowedPaths: ['/home/user/docs'] });
const governedServer = plugin.wrap(rawServer, engine);
createServer(governedServer).listen();
```

Restart Claude Desktop after editing the config file.

---

## Cursor IDE

Cursor reads MCP server configuration from `.cursor/mcp.json` in your project
root, or from `~/.cursor/mcp.json` for a global configuration.

```json
{
  "mcpServers": {
    "governed-tools": {
      "command": "node",
      "args": ["./mcp/governed-entry.js"],
      "env": {
        "AUMOS_AGENT_ID": "cursor-workspace"
      }
    }
  }
}
```

The entry script follows the same pattern as the Claude Desktop example above.
Place `governed-entry.js` at `./mcp/governed-entry.js` relative to your project
root, or use an absolute path in `args`.

**Per-project vs global:**
- `.cursor/mcp.json` — applies only to the current workspace.
- `~/.cursor/mcp.json` — applies to all Cursor workspaces.

---

## Windsurf

Windsurf uses a `mcp_config.json` file. The default location is
`~/.codeium/windsurf/mcp_config.json`.

```json
{
  "mcpServers": {
    "governed-tools": {
      "command": "node",
      "args": ["/absolute/path/to/governed-entry.js"],
      "env": {
        "AUMOS_AGENT_ID": "windsurf-session"
      }
    }
  }
}
```

Windsurf starts MCP servers as child processes of the IDE process. Environment
variables set in `env` are merged with the IDE's own environment.

---

## Cline (VS Code Extension)

Cline stores its MCP server list in VS Code's `settings.json` under the
`cline.mcpServers` key. Open the VS Code settings JSON
(`Ctrl+Shift+P` → "Open User Settings (JSON)") and add:

```json
{
  "cline.mcpServers": {
    "governed-tools": {
      "command": "node",
      "args": ["/absolute/path/to/governed-entry.js"],
      "env": {
        "AUMOS_AGENT_ID": "cline-vscode"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

Cline also supports workspace-level configuration via
`.vscode/settings.json` — the same structure applies there.

---

## Generic MCP Client Setup

Any MCP client that launches server processes accepts the same pattern:

1. **Write a governed entry script** that:
   - Imports your real MCP server.
   - Instantiates a `GovernanceEngine`.
   - Instantiates `OpenClawGovernancePlugin` with your policy.
   - Wraps the server with `plugin.wrap(server, engine)`.
   - Passes the governed server to your MCP transport (stdio, SSE, etc.).

2. **Point the client** at your entry script via its `command` / `args` config.

3. **Set `AUMOS_AGENT_ID`** in the client's environment config. This value
   appears in every audit record and trust lookup.

```js
// governed-entry.js — generic template
import { OpenClawGovernancePlugin } from '@aumos/openclaw-governance';
import { GovernanceEngine, GovernanceEngineConfig } from '@aumos/governance';

const engine = new GovernanceEngine(new GovernanceEngineConfig());

const plugin = new OpenClawGovernancePlugin({
  agentId: process.env.AUMOS_AGENT_ID ?? 'mcp-client',
  trustRequirements: {},   // fill in per-tool requirements
  budgetCategories: {},    // fill in per-tool budget categories
  onDenied: 'message',
});

// Import and wrap YOUR server here, then connect to your transport.
```

---

## Configuration Reference

| Field | Type | Default | Description |
|---|---|---|---|
| `agentId` | `string` | required | Identifier for the calling agent. Appears in all audit records. |
| `trustRequirements` | `Record<string, number>` | `{}` | Per-tool minimum trust level (0–5). Tools not listed are always permitted. |
| `budgetCategories` | `Record<string, string>` | `{}` | Maps tool names to budget category labels. Tools not listed skip budget checks. |
| `onDenied` | `'error' \| 'message'` | `'message'` | `'error'` throws `GovernanceDeniedError`. `'message'` returns a denial text result. |

**Trust level convention (operator-defined):**

| Level | Suggested meaning |
|---|---|
| 0 | No restriction |
| 1 | Read-only operations |
| 2 | Write operations |
| 3 | Destructive or privileged operations |
| 4 | System-level or cross-user operations |
| 5 | Reserved for highest-privilege operations |

Trust levels are assigned manually by your governance operator. The plugin
reads them; it never changes them.

---

## Per-Client Installation Summary

| Client | Config file | Restart required |
|---|---|---|
| Claude Desktop | `claude_desktop_config.json` | Yes — full app restart |
| Cursor | `.cursor/mcp.json` or `~/.cursor/mcp.json` | Yes — reload window |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | Yes — reload window |
| Cline (VS Code) | `settings.json` → `cline.mcpServers` | No — Cline reloads on save |

---

## Further Reading

- [IDE AI Governance Guide](ide-ai-governance.md)
- [OpenClaw API Reference](configuration.md)
- Full docs: [https://docs.aumos.ai/integrations/openclaw](https://docs.aumos.ai/integrations/openclaw)

---

Copyright (c) 2026 MuVeraAI Corporation. Apache 2.0.
