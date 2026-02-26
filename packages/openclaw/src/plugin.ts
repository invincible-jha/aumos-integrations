// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 MuVeraAI Corporation

import type { GovernanceEngine } from '@aumos/governance';
import { parsePluginConfig } from './config.js';
import type { PluginConfigInput } from './config.js';
import { createGovernedProxy } from './interceptor.js';
import type { MCPServer, GovernanceDecision, InterceptorConfig } from './types.js';

// ---------------------------------------------------------------------------
// OpenClawGovernancePlugin
// ---------------------------------------------------------------------------

/**
 * Enterprise governance plugin for OpenClaw MCP servers.
 *
 * Wraps any MCPServer-compatible object with a Proxy that enforces trust and
 * budget policies on every callTool invocation, and records every governance
 * decision to the audit trail.
 *
 * Usage:
 * ```typescript
 * import { createGovernanceEngine } from '@aumos/governance';
 * import { OpenClawGovernancePlugin } from '@aumos/openclaw-governance';
 *
 * const engine = createGovernanceEngine({ agentId: 'my-agent' });
 * const plugin = new OpenClawGovernancePlugin(engine, {
 *   agentId: 'my-agent',
 *   trustRequirements: { 'fs_write': 3, 'shell_exec': 4 },
 *   budgetCategories: { 'fs_write': 'storage', 'web_search': 'network' },
 *   onDenied: 'message',
 * });
 *
 * const governedServer = plugin.wrap(myMcpServer);
 * // governedServer.callTool is now governed
 * ```
 *
 * The plugin never modifies trust levels, never auto-promotes agents, and
 * never performs behavioral scoring. All trust assignments are manual and
 * performed via the GovernanceEngine's trust manager outside this plugin.
 */
export class OpenClawGovernancePlugin {
  private readonly engine: GovernanceEngine;
  private readonly interceptorConfig: InterceptorConfig;

  /**
   * Construct a new governance plugin.
   *
   * @param engine - A fully initialised GovernanceEngine from @aumos/governance.
   *                 The engine provides trust checking, budget checking, and
   *                 audit logging. It must outlive the plugin instance.
   * @param config - Plugin configuration. agentId is required; all other
   *                 fields default to safe empty values if omitted.
   * @throws ZodError if config fails validation.
   */
  constructor(engine: GovernanceEngine, config: PluginConfigInput) {
    this.engine = engine;

    // Parse and validate at construction time so errors surface immediately,
    // not on the first tool call.
    const validated = parsePluginConfig(config);

    this.interceptorConfig = {
      agentId: validated.agentId,
      trustRequirements: validated.trustRequirements,
      budgetCategories: validated.budgetCategories,
      onDenied: validated.onDenied,
    };
  }

  /**
   * Wrap an MCP server with governance enforcement.
   *
   * Returns a Proxy that is structurally identical to the original server T
   * but intercepts every `callTool` invocation to evaluate trust and budget
   * policies before forwarding.
   *
   * The original server object is not mutated. Multiple wrap() calls can
   * produce independent governed views of the same underlying server.
   *
   * @param server - Any object implementing the MCPServer interface.
   * @returns A governed Proxy of the same type T.
   */
  public wrap<T extends MCPServer>(server: T): T {
    return createGovernedProxy(server, this.engine, this.interceptorConfig);
  }

  /**
   * Evaluate governance for a prospective tool call without executing it.
   *
   * Useful for pre-flight checks in UI layers, or for testing policy
   * configuration without side effects.
   *
   * This method does NOT record anything to the audit trail — it is purely
   * a read-only evaluation. The audit trail only captures decisions that
   * accompany real callTool invocations via wrap().
   *
   * @param toolName - MCP tool name to evaluate.
   * @param args     - Optional arguments (currently unused in evaluation;
   *                   included for forward-compatibility with argument-aware
   *                   policies).
   * @returns A GovernanceDecision describing whether the call would be permitted.
   */
  public async check(
    toolName: string,
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    _args?: unknown,
  ): Promise<GovernanceDecision> {
    // ---- Trust check ----
    const requiredTrustLevel =
      this.interceptorConfig.trustRequirements[toolName];

    if (requiredTrustLevel !== undefined) {
      const trustResult = await this.engine.trust.checkLevel(
        this.interceptorConfig.agentId,
        requiredTrustLevel,
      );

      if (!trustResult.permitted) {
        return {
          permitted: false,
          toolName,
          reason: `Trust level ${trustResult.effectiveLevel} is below required ${requiredTrustLevel}`,
          trustLevel: trustResult.effectiveLevel,
        };
      }

      // Trust passed — continue to budget check with trust level captured.
      const budgetDecision = await this.checkBudget(toolName);
      return {
        ...budgetDecision,
        trustLevel: trustResult.effectiveLevel,
      };
    }

    // No trust requirement — go straight to budget check.
    return this.checkBudget(toolName);
  }

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  /**
   * Perform the budget portion of a check() evaluation.
   * Returns a partial GovernanceDecision (no trustLevel field — caller adds it).
   */
  private async checkBudget(toolName: string): Promise<GovernanceDecision> {
    const category = this.interceptorConfig.budgetCategories[toolName];

    if (category === undefined) {
      return {
        permitted: true,
        toolName,
        reason: 'Permitted: no governance requirements configured for this tool',
      };
    }

    const unitCost = 1;
    const budgetResult = await this.engine.budget.checkBudget(
      category,
      unitCost,
    );

    if (!budgetResult.permitted) {
      return {
        permitted: false,
        toolName,
        budgetImpact: unitCost,
        reason: `Budget exhausted for category '${category}' (available: ${budgetResult.available}, requested: ${unitCost})`,
      };
    }

    return {
      permitted: true,
      toolName,
      budgetImpact: unitCost,
      reason: `Permitted — budget check passed for category '${category}' (available: ${budgetResult.available})`,
    };
  }
}
