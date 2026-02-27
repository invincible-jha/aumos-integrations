# Governing AI in Your IDE

IDE-embedded AI assistants — Copilot, Cursor, Cline, Windsurf, and others —
execute tool calls directly against your local file system, shell, and external
APIs. Without governance, every AI action in your IDE happens with the same
permissions as your user account.

This guide explains why IDE AI needs governance, what controls AumOS provides
through the OpenClaw plugin, and how to reason about policy for the most common
IDE AI actions.

---

## Why IDE AI Assistants Need Governance

An IDE AI assistant with MCP server access can:

- Read, overwrite, or delete any file your OS user can access.
- Execute shell commands.
- Make authenticated API calls with your stored credentials.
- Send data to external services (search, documentation, model APIs).

These capabilities are necessary for the assistant to be useful. Governance does
not remove them. It adds a **checkpoint** between the model's intent and
execution so that your stated policy is enforced — not assumed.

Three problems governance addresses:

**1. Prompt injection.** A malicious document, web page, or API response can
instruct the AI to perform actions the user did not request. A trust gate checks
whether the agent is authorized for the requested tool at the configured level —
it does not matter what the model was told to do.

**2. Accidental destructive actions.** Code-writing agents often have access to
both file-write and file-delete tools. A budget cap or trust requirement on
destructive tools means the assistant cannot perform them without explicit
authorization, regardless of how confident it is.

**3. API cost overruns.** When AI-assisted workflows call external APIs (web
search, vector databases, LLM completions), uncapped usage can result in
unexpected bills. Static budget envelopes give you a hard ceiling per session or
per category.

---

## Trust Levels for Code Generation vs Code Execution

Not all IDE AI actions carry the same risk. A graduated trust model lets you
approve low-risk actions (reading a file, searching documentation) without the
same authorization overhead as high-risk ones (running a shell command, writing
to a production config file).

Recommended starting points — adjust to your own threat model:

| Trust Level | Actions at this level |
|---|---|
| 0 | List directory, read documentation, read non-sensitive files |
| 1 | Read any file in the workspace, run read-only queries |
| 2 | Write files, create new files, insert code |
| 3 | Delete files, modify dotfiles, overwrite configuration |
| 4 | Execute shell commands, run tests, install packages |
| 5 | Deploy, push to remote repositories, access secrets |

Trust levels are assigned to the agent identity (`agentId`) by the operator —
you, in a local IDE context. They are set once in your governance configuration
and never modified automatically at runtime.

**Code generation** (writing files) typically sits at level 2. The AI needs
write access to be useful, but that access should be explicit.

**Code execution** (running the generated code via shell) is higher risk. A
reasonable default is level 4, requiring deliberate operator sign-off before the
assistant can run arbitrary commands.

---

## Budget Caps for API Costs

Each tool call can be mapped to a named budget category. The governance engine
maintains a static spending envelope per category. When the envelope is
exhausted, calls in that category are denied until the operator resets or
increases the limit.

Example categories for an IDE AI configuration:

| Category | Tools mapped | Suggested cap |
|---|---|---|
| `web_search` | `search`, `fetch_url` | 50 calls / session |
| `llm_completion` | `ask_model`, `summarise` | 20 calls / session |
| `file_write` | `write_file`, `create_file` | 200 calls / session |
| `shell_exec` | `run_command`, `run_tests` | 10 calls / session |

Caps are static integers set in your `OpenClawGovernancePlugin` configuration.
The plugin does not adjust them based on usage patterns. When a cap is hit, the
denial is recorded in the audit trail and returned to the AI client as a denial
message.

---

## Consent for Code Touching User Data

When your workspace contains files that hold personally identifiable information
(PII) — user records, credentials, exported datasets — you may want to require
explicit authorization before the AI reads or modifies them.

OpenClaw supports this through `trustRequirements` at the per-tool level. If
your sensitive files are accessed via a dedicated MCP tool (e.g., a
`read_user_records` tool exposed by a data-access server), you can set a higher
trust level for that tool than for general file reads:

```js
trustRequirements: {
  read_file: 1,          // general file reads: level 1
  read_user_records: 3,  // PII-adjacent reads: level 3
  write_user_records: 4, // PII writes: level 4
}
```

The operator raises the agent's trust level to 3 or 4 only when an explicit
data-processing session is under way. Outside those sessions, the agent's level
stays at 1 — the AI can read code files freely but not user data.

---

## Architecture: MCP Client to Trust Gate to Tool

```
+--------------------+
|   IDE / MCP Client |   (Claude Desktop, Cursor, Cline, Windsurf)
|   sends tool call  |
+--------+-----------+
         |  callTool("write_file", { path: "...", content: "..." })
         v
+-----------------------------+
|  OpenClawGovernancePlugin   |   (@aumos/openclaw-governance)
|                             |
|  1. Trust gate              |   Is agent level >= trustRequirements["write_file"]?
|     checkLevel(agentId, 2)  |   -> Permitted: level 2 >= required 2
|                             |
|  2. Budget gate             |   Does "file_write" envelope have capacity?
|     checkBudget("file_write", 1)  -> Permitted: 147 remaining
|                             |
|  3. Audit record            |   Append decision to audit trail (recording only)
|     audit.log(...)          |
+--------+--------------------+
         |  permitted — forward call
         v
+--------------------+
|   Real MCP Server  |   (filesystem server, shell server, etc.)
|   executes tool    |
+--------------------+
         |
         v  result returned to MCP client

[On denial: plugin returns a denial message to the client instead of forwarding]
```

The governance plugin sits entirely in the Node.js process that bridges your
MCP client to the underlying tool server. No governance logic runs inside the
AI model. The model receives either the tool result or a denial message —
it cannot distinguish a governance denial from a normal tool error.

---

## Quick Setup Reference

1. Install: `npm install @aumos/openclaw-governance @aumos/governance`
2. Write a governed entry script (see the [Universal MCP Client Guide](universal-mcp-client.md)).
3. Set `agentId`, `trustRequirements`, and `budgetCategories` for your workflow.
4. Point your IDE's MCP config at the entry script.
5. Set your agent's initial trust level on the `GovernanceEngine` before starting
   the session. Trust levels are never set automatically.

---

## Further Reading

- [Universal MCP Client Guide](universal-mcp-client.md) — per-client config steps
- [Configuration Reference](configuration.md) — full plugin API
- Full docs: [https://docs.aumos.ai/integrations/openclaw](https://docs.aumos.ai/integrations/openclaw)

---

Copyright (c) 2026 MuVeraAI Corporation. Apache 2.0.
