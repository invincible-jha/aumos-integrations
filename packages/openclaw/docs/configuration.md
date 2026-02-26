# Configuration Reference — @aumos/openclaw-governance

## PluginConfig

```typescript
interface PluginConfigInput {
  agentId: string;
  trustRequirements?: Record<string, number>;
  budgetCategories?: Record<string, string>;
  onDenied?: 'error' | 'message';
}
```

All fields except `agentId` are optional and default to safe empty values.

---

### `agentId` (required)

**Type:** `string` (non-empty)

The identifier of the agent being governed. Must match the agent ID used when
calling `engine.trust.setLevel()` and when creating budget envelopes.

```typescript
{ agentId: 'my-agent-01' }
```

---

### `trustRequirements` (optional)

**Type:** `Record<string, number>`
**Default:** `{}` (no trust requirements — all tools permitted at any level)

Maps MCP tool names to the minimum trust level an agent must hold to call that
tool. Trust levels are integers from 0 to 5:

| Level | Name               | Capability                              |
|-------|--------------------|-----------------------------------------|
| 0     | OBSERVER           | Read-only observation                   |
| 1     | MONITOR            | State monitoring and status signaling   |
| 2     | SUGGEST            | Recommendation generation               |
| 3     | ACT_WITH_APPROVAL  | Action execution with human approval    |
| 4     | ACT_AND_REPORT     | Action execution with mandatory reporting |
| 5     | AUTONOMOUS         | Full autonomous execution               |

Tools absent from this map are permitted at any trust level.

```typescript
trustRequirements: {
  list_files:    1,   // MONITOR — low bar for read operations
  write_file:    3,   // ACT_WITH_APPROVAL — write operations need higher trust
  delete_file:   5,   // AUTONOMOUS — destructive ops need full grant
  execute_shell: 5,
}
```

Trust levels are set by human operators via `engine.trust.setLevel()`.
This plugin never modifies trust levels.

---

### `budgetCategories` (optional)

**Type:** `Record<string, string>`
**Default:** `{}` (no budget enforcement)

Maps MCP tool names to budget category identifiers. A call to a mapped tool
draws one unit from the corresponding spending envelope.

Budget envelopes must be created via `engine.budget.createBudget()` before any
governed call is made. If a tool is mapped to a category but no envelope exists
for that category, the budget check will report the category as exhausted.

Tools absent from this map are not subject to budget enforcement.

```typescript
budgetCategories: {
  web_search:    'network',    // draws from the 'network' envelope
  fetch_url:     'network',    // same envelope as web_search
  run_analysis:  'compute',
}
```

Budget envelopes are static. Limits are set at creation time and are not
adjusted automatically by this plugin.

---

### `onDenied` (optional)

**Type:** `'error' | 'message'`
**Default:** `'message'`

Controls what happens when a tool call is denied by governance:

- `'message'` — the intercepted `callTool` returns a synthetic `MCPToolResult`
  with `isError: true` and a human-readable denial message in `content[0].text`.
  The calling code sees a normal result and must inspect `isError` to detect denial.

- `'error'` — the intercepted `callTool` throws a `GovernanceDeniedError`.
  The calling code's `try/catch` fires. The error object carries the full
  `GovernanceDecision` on its `.decision` property.

Use `'message'` when your orchestration layer handles errors inline.
Use `'error'` when you want governance denials to propagate up the call stack
like any other exception.

---

## InterceptorConfig

The lower-level `createGovernedProxy()` function accepts an `InterceptorConfig`
directly. This is the validated, resolved form of `PluginConfigInput` — all
fields are required with no optional defaults.

```typescript
interface InterceptorConfig {
  readonly agentId: string;
  readonly trustRequirements: Readonly<Record<string, number>>;
  readonly budgetCategories: Readonly<Record<string, string>>;
  readonly onDenied: 'error' | 'message';
}
```

Use `createGovernedProxy` when you need to construct the interceptor config
outside of the plugin lifecycle, or when wrapping servers with different
configurations from the same engine instance.

---

## GovernanceDecision

Returned by `plugin.check()` and carried on `GovernanceDeniedError.decision`:

```typescript
interface GovernanceDecision {
  readonly permitted: boolean;
  readonly reason: string;
  readonly toolName: string;
  readonly trustLevel?: number;
  readonly budgetImpact?: number;
}
```

- `permitted` — `true` if the call would be allowed, `false` if denied.
- `reason` — human-readable explanation, always present.
- `toolName` — the MCP tool that was evaluated.
- `trustLevel` — agent's effective trust level at evaluation time (present when
  a trust requirement is configured for the tool).
- `budgetImpact` — cost that would be charged (present when a budget category is
  configured for the tool).

---

## MCPServer interface

Any object passed to `plugin.wrap()` or `createGovernedProxy()` must satisfy:

```typescript
interface MCPServer {
  callTool(name: string, args: unknown): Promise<MCPToolResult>;
}
```

This minimal interface avoids a hard dependency on any specific MCP SDK version.
The real OpenClaw server satisfies this interface natively.
