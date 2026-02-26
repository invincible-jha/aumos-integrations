// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 MuVeraAI Corporation

/**
 * Basic governance example — wrap an MCP server and enforce policies.
 *
 * Demonstrates:
 * - Setting up an engine with manual trust assignment
 * - Wrapping a mock MCP server with governance
 * - Observing permit and deny outcomes via the 'message' mode
 */

import { createGovernanceEngine } from '@aumos/governance';
import { OpenClawGovernancePlugin } from '@aumos/openclaw-governance';
import type { MCPServer, MCPToolResult } from '@aumos/openclaw-governance';

// ---------------------------------------------------------------------------
// Stub MCP server — replace with your real OpenClaw server instance
// ---------------------------------------------------------------------------

const stubServer: MCPServer = {
  async callTool(name: string, args: unknown): Promise<MCPToolResult> {
    console.log(`[real-server] Executing tool '${name}' with args:`, args);
    return {
      content: [{ type: 'text', text: `Tool '${name}' executed successfully.` }],
    };
  },
};

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  const agentId = 'demo-agent-01';

  // Create the governance engine. The engine holds trust, budget, and audit
  // state in memory for this process lifetime.
  const engine = createGovernanceEngine({ agentId });

  // Manually assign a trust level of 2 (SUGGEST) to the agent.
  // Trust is ALWAYS set by a human operator — never automatic.
  await engine.trust.setLevel(agentId, 2, {
    reason: 'Initial onboarding — read-only reconnaissance phase',
    assignedBy: 'ops-team',
  });

  // Create a budget envelope so we can demonstrate budget-based governance.
  await engine.budget.createBudget({
    category: 'network',
    limit: 3,
    period: 'daily',
  });

  // Construct the plugin.
  // - web_search requires trust level 1 (MONITOR) and draws from 'network'.
  // - fs_write requires trust level 3 (ACT_WITH_APPROVAL) — agent will be denied.
  // - shell_exec has no mapping — permitted at any trust level, no budget check.
  const plugin = new OpenClawGovernancePlugin(engine, {
    agentId,
    trustRequirements: {
      web_search: 1,
      fs_write: 3,
    },
    budgetCategories: {
      web_search: 'network',
    },
    onDenied: 'message',
  });

  // Wrap the server — the governed proxy is structurally identical to stubServer.
  const governed = plugin.wrap(stubServer);

  // ---- Case 1: web_search — agent has level 2, requires 1 → PERMIT ----
  console.log('\n--- Case 1: web_search (trust OK, budget available) ---');
  const result1 = await governed.callTool('web_search', { query: 'governance patterns' });
  console.log('isError:', result1.isError ?? false);
  console.log('response:', result1.content[0]?.text);

  // ---- Case 2: fs_write — agent has level 2, requires 3 → DENY ----
  console.log('\n--- Case 2: fs_write (trust too low) ---');
  const result2 = await governed.callTool('fs_write', { path: '/tmp/out.txt', content: 'hello' });
  console.log('isError:', result2.isError ?? false);
  console.log('response:', result2.content[0]?.text);

  // ---- Case 3: shell_exec — no policy configured → PERMIT ----
  console.log('\n--- Case 3: shell_exec (no policy configured) ---');
  const result3 = await governed.callTool('shell_exec', { command: 'echo hi' });
  console.log('isError:', result3.isError ?? false);
  console.log('response:', result3.content[0]?.text);

  // ---- Case 4: web_search — exhaust budget (limit is 3, already spent 1) ----
  console.log('\n--- Case 4+5+6: exhaust web_search budget ---');
  await governed.callTool('web_search', { query: 'second call' });
  await governed.callTool('web_search', { query: 'third call' });
  const result6 = await governed.callTool('web_search', { query: 'fourth call — over budget' });
  console.log('isError:', result6.isError ?? false);
  console.log('response:', result6.content[0]?.text);

  // ---- Pre-flight check using plugin.check() ----
  console.log('\n--- Pre-flight check for web_search ---');
  const preflight = await plugin.check('web_search');
  console.log('would be permitted:', preflight.permitted);
  console.log('reason:', preflight.reason);
}

main().catch(console.error);
