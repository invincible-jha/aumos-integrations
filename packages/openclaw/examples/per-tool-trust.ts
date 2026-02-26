// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 MuVeraAI Corporation

/**
 * Per-tool trust example — demonstrate fine-grained trust level requirements.
 *
 * Demonstrates:
 * - Different tools requiring different minimum trust levels
 * - The onDenied: 'error' mode that throws GovernanceDeniedError
 * - Using plugin.check() before making calls from UI / orchestration code
 * - Using createGovernedProxy directly for custom integration scenarios
 */

import { createGovernanceEngine } from '@aumos/governance';
import {
  OpenClawGovernancePlugin,
  createGovernedProxy,
  GovernanceDeniedError,
} from '@aumos/openclaw-governance';
import type { MCPServer, MCPToolResult } from '@aumos/openclaw-governance';

// ---------------------------------------------------------------------------
// Stub MCP server
// ---------------------------------------------------------------------------

const stubServer: MCPServer = {
  async callTool(name: string, _args: unknown): Promise<MCPToolResult> {
    return {
      content: [{ type: 'text', text: `[executed] ${name}` }],
    };
  },
};

// ---------------------------------------------------------------------------
// Helper — display check result
// ---------------------------------------------------------------------------

function displayCheck(toolName: string, permitted: boolean, reason: string): void {
  const label = permitted ? 'PERMIT' : 'DENY';
  console.log(`  ${label.padEnd(6)} ${toolName.padEnd(20)} — ${reason}`);
}

// ---------------------------------------------------------------------------
// Example 1 — Per-tool trust requirements with error mode
// ---------------------------------------------------------------------------

async function runErrorModeExample(): Promise<void> {
  console.log('\n=== Example 1: Per-tool trust requirements (onDenied: error) ===\n');

  const agentId = 'analyst-agent';
  const engine = createGovernanceEngine({ agentId });

  // Assign trust level 3 (ACT_WITH_APPROVAL) — enough for most tools.
  await engine.trust.setLevel(agentId, 3, {
    reason: 'Promoted after manual code review of agent outputs',
    assignedBy: 'security-lead',
  });

  const plugin = new OpenClawGovernancePlugin(engine, {
    agentId,
    trustRequirements: {
      // Read tools: low trust bar
      list_directory: 1,
      read_file: 1,
      web_search: 1,
      // Write tools: higher trust bar
      write_file: 3,
      create_directory: 3,
      // Destructive tools: require full autonomy grant
      delete_file: 5,
      execute_script: 5,
    },
    onDenied: 'error',
  });

  // Pre-flight — check all tools before calling any
  console.log('Pre-flight trust checks (agent trust level: 3):');
  const toolsToCheck = [
    'list_directory', 'read_file', 'web_search',
    'write_file', 'create_directory',
    'delete_file', 'execute_script',
  ];

  for (const tool of toolsToCheck) {
    const decision = await plugin.check(tool);
    displayCheck(tool, decision.permitted, decision.reason);
  }

  // Execute a permitted tool
  const governed = plugin.wrap(stubServer);
  console.log('\nExecuting permitted tool (write_file)...');
  const writeResult = await governed.callTool('write_file', { path: '/tmp/report.md' });
  console.log('Result:', writeResult.content[0]?.text);

  // Execute a denied tool — catch GovernanceDeniedError
  console.log('\nAttempting denied tool (delete_file)...');
  try {
    await governed.callTool('delete_file', { path: '/tmp/report.md' });
  } catch (error) {
    if (error instanceof GovernanceDeniedError) {
      console.log('Caught GovernanceDeniedError:');
      console.log('  toolName:', error.decision.toolName);
      console.log('  reason:  ', error.decision.reason);
      console.log('  trustLevel:', error.decision.trustLevel);
    } else {
      throw error;
    }
  }
}

// ---------------------------------------------------------------------------
// Example 2 — Using createGovernedProxy directly (lower-level API)
// ---------------------------------------------------------------------------

async function runDirectProxyExample(): Promise<void> {
  console.log('\n=== Example 2: Direct proxy usage (createGovernedProxy) ===\n');

  const agentId = 'automation-bot';
  const engine = createGovernanceEngine({ agentId });

  await engine.trust.setLevel(agentId, 4, {
    reason: 'Validated automation pipeline — post-hoc reporting enabled',
    assignedBy: 'platform-admin',
  });

  await engine.budget.createBudget({
    category: 'compute',
    limit: 5,
    period: 'hourly',
  });

  // Use the lower-level factory directly, bypassing the plugin class.
  // Useful when you need more control over the InterceptorConfig lifecycle.
  const governed = createGovernedProxy(stubServer, engine, {
    agentId,
    trustRequirements: { run_analysis: 4 },
    budgetCategories: { run_analysis: 'compute' },
    onDenied: 'message',
  });

  console.log('Calling run_analysis (trust: 4/4, budget: 5 remaining)...');
  for (let callNumber = 1; callNumber <= 6; callNumber++) {
    const result = await governed.callTool('run_analysis', { jobId: `job-${callNumber}` });
    const status = result.isError === true ? 'DENIED' : 'PERMIT';
    console.log(`  Call ${callNumber}: [${status}] ${result.content[0]?.text}`);
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  await runErrorModeExample();
  await runDirectProxyExample();
}

main().catch(console.error);
