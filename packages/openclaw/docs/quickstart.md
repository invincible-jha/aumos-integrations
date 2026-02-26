# Quickstart — @aumos/openclaw-governance

Add enterprise governance to any OpenClaw MCP server in three steps.

## Prerequisites

- Node.js >= 20
- `@aumos/governance` >= 0.1.0 installed in your project

## Installation

```bash
npm install @aumos/openclaw-governance @aumos/governance
```

## Step 1 — Create a governance engine

```typescript
import { createGovernanceEngine } from '@aumos/governance';

const engine = createGovernanceEngine({ agentId: 'my-agent' });

// Assign a trust level manually (always done by a human operator).
await engine.trust.setLevel('my-agent', 3, {
  reason: 'Reviewed and approved for write operations',
  assignedBy: 'ops-lead',
});

// Optional: create a budget envelope.
await engine.budget.createBudget({
  category: 'network',
  limit: 100,
  period: 'daily',
});
```

## Step 2 — Configure and create the plugin

```typescript
import { OpenClawGovernancePlugin } from '@aumos/openclaw-governance';

const plugin = new OpenClawGovernancePlugin(engine, {
  agentId: 'my-agent',

  // Minimum trust level required per tool (omit a tool to allow it at any level).
  trustRequirements: {
    web_search: 1,
    write_file: 3,
    delete_file: 5,
  },

  // Budget category per tool (omit a tool to skip budget enforcement).
  budgetCategories: {
    web_search: 'network',
  },

  // 'message' returns a denial response; 'error' throws GovernanceDeniedError.
  onDenied: 'message',
});
```

## Step 3 — Wrap your MCP server

```typescript
import type { MCPServer } from '@aumos/openclaw-governance';

// Replace with your real OpenClaw server instance.
const myMcpServer: MCPServer = getOpenClawServer();

const governed = plugin.wrap(myMcpServer);

// Now use governed exactly like myMcpServer.
const result = await governed.callTool('web_search', { query: 'governance patterns' });
```

If the tool call is denied, `result.isError` is `true` and `result.content[0].text`
contains a human-readable denial message.

## Pre-flight checks

Use `plugin.check()` to evaluate a prospective call without executing it.
This is useful in UI layers where you want to show/hide actions based on policy.

```typescript
const decision = await plugin.check('delete_file');
if (!decision.permitted) {
  showDisabledState(`Cannot delete: ${decision.reason}`);
}
```

## Error mode

If you prefer exceptions over denial responses, set `onDenied: 'error'`:

```typescript
import { GovernanceDeniedError } from '@aumos/openclaw-governance';

try {
  await governed.callTool('delete_file', { path: '/data/important.db' });
} catch (error) {
  if (error instanceof GovernanceDeniedError) {
    console.log('Denied:', error.decision.reason);
    console.log('Tool:', error.decision.toolName);
    console.log('Trust level:', error.decision.trustLevel);
  }
}
```

## Next steps

- See [configuration.md](./configuration.md) for the full configuration reference.
- See `examples/basic-governance.ts` and `examples/per-tool-trust.ts` for runnable examples.
