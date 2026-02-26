// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 MuVeraAI Corporation

import type { GovernanceEngine } from '@aumos/governance';
import type {
  MCPServer,
  MCPToolResult,
  GovernanceDecision,
  InterceptorConfig,
} from './types.js';
import { GovernanceDeniedError } from './types.js';

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Evaluate trust requirements for the given tool call.
 *
 * Returns a partial GovernanceDecision fragment indicating whether the trust
 * gate passed, along with the agent's effective trust level if a check was
 * performed.
 *
 * Trust is checked by calling engine.trust.checkLevel() — a read-only method
 * that never mutates state. Level assignment is always done by a human
 * operator outside this plugin.
 */
async function evaluateTrust(
  engine: GovernanceEngine,
  agentId: string,
  toolName: string,
  trustRequirements: Readonly<Record<string, number>>,
): Promise<{ permitted: boolean; reason: string; trustLevel?: number }> {
  const requiredLevel = trustRequirements[toolName];

  if (requiredLevel === undefined) {
    // No trust requirement configured for this tool — pass through.
    return { permitted: true, reason: 'No trust requirement for this tool' };
  }

  const checkResult = await engine.trust.checkLevel(agentId, requiredLevel);

  return {
    permitted: checkResult.permitted,
    trustLevel: checkResult.effectiveLevel,
    reason: checkResult.permitted
      ? `Trust level ${checkResult.effectiveLevel} meets required ${requiredLevel}`
      : `Trust level ${checkResult.effectiveLevel} is below required ${requiredLevel}`,
  };
}

/**
 * Evaluate budget requirements for the given tool call.
 *
 * Calls engine.budget.checkBudget() with a unit cost of 1 when a budget
 * category is mapped for the tool. Returns a partial decision fragment.
 *
 * Budget state is read-only during check; actual spend is recorded via
 * engine.budget.recordSpending() only after a permitted decision.
 */
async function evaluateBudget(
  engine: GovernanceEngine,
  toolName: string,
  budgetCategories: Readonly<Record<string, string>>,
): Promise<{ permitted: boolean; reason: string; budgetImpact?: number }> {
  const category = budgetCategories[toolName];

  if (category === undefined) {
    // No budget category configured for this tool — pass through.
    return { permitted: true, reason: 'No budget category for this tool' };
  }

  const unitCost = 1;
  const checkResult = await engine.budget.checkBudget(category, unitCost);

  return {
    permitted: checkResult.permitted,
    budgetImpact: unitCost,
    reason: checkResult.permitted
      ? `Budget check passed for category '${category}' (available: ${checkResult.available})`
      : `Budget exhausted for category '${category}' (available: ${checkResult.available}, requested: ${unitCost})`,
  };
}

/**
 * Record spending against the budget envelope after a permitted tool call.
 * Silently absorbs errors — a failed record should not retroactively deny
 * an already-permitted call, but the error is surfaced to the console so
 * operators can investigate.
 */
async function recordBudgetSpend(
  engine: GovernanceEngine,
  toolName: string,
  budgetCategories: Readonly<Record<string, string>>,
): Promise<void> {
  const category = budgetCategories[toolName];
  if (category === undefined) return;

  try {
    await engine.budget.recordSpending(category, 1);
  } catch (error) {
    console.error(
      `[openclaw-governance] Failed to record budget spend for tool '${toolName}' category '${category}':`,
      error,
    );
  }
}

/**
 * Append a governance decision to the audit trail.
 * Silently absorbs errors — audit failures must not block tool execution.
 */
async function auditDecision(
  engine: GovernanceEngine,
  agentId: string,
  toolName: string,
  decision: GovernanceDecision,
): Promise<void> {
  try {
    await engine.audit.log({
      agentId,
      action: toolName,
      permitted: decision.permitted,
      ...(decision.trustLevel !== undefined
        ? { trustLevel: decision.trustLevel }
        : {}),
      ...(decision.budgetImpact !== undefined
        ? { budgetUsed: decision.budgetImpact }
        : {}),
      reason: decision.reason,
    });
  } catch (error) {
    console.error(
      `[openclaw-governance] Failed to write audit record for tool '${toolName}':`,
      error,
    );
  }
}

// ---------------------------------------------------------------------------
// Denial response builders
// ---------------------------------------------------------------------------

/**
 * Build a synthetic MCPToolResult that signals denial to the caller without
 * throwing. Used when onDenied is 'message'.
 */
function buildDenialResult(decision: GovernanceDecision): MCPToolResult {
  return {
    content: [
      {
        type: 'text',
        text: `[governance] Tool call '${decision.toolName}' was denied: ${decision.reason}`,
      },
    ],
    isError: true,
  };
}

// ---------------------------------------------------------------------------
// Public factory — createGovernedProxy
// ---------------------------------------------------------------------------

/**
 * Wrap an MCP server object with a JavaScript Proxy that enforces governance
 * on every callTool invocation.
 *
 * The Proxy intercepts only the `callTool` property. All other method and
 * property accesses are forwarded transparently via Reflect.get so the
 * wrapped server continues to behave as its original type T.
 *
 * Governance evaluation order:
 *   1. Trust check  — is the agent's level >= the tool's requirement?
 *   2. Budget check — does the relevant spending envelope have capacity?
 *   3. Audit log    — record the decision (permit or deny) in the trail.
 *   4. Execution    — forward to the real server only if both checks pass.
 *   5. Budget spend — record actual spend after successful execution.
 *
 * @param server  - The real MCP server to wrap.
 * @param engine  - A fully initialised GovernanceEngine from @aumos/governance.
 * @param config  - Validated interceptor configuration.
 * @returns A Proxy that is structurally identical to T but governed.
 */
export function createGovernedProxy<T extends MCPServer>(
  server: T,
  engine: GovernanceEngine,
  config: InterceptorConfig,
): T {
  return new Proxy(server, {
    get(target, prop, receiver) {
      if (prop !== 'callTool') {
        return Reflect.get(target, prop, receiver) as unknown;
      }

      // Return a governed replacement for callTool.
      return async (toolName: string, args: unknown): Promise<MCPToolResult> => {
        // ----------------------------------------------------------------
        // Step 1 — Trust evaluation
        // ----------------------------------------------------------------
        const trustResult = await evaluateTrust(
          engine,
          config.agentId,
          toolName,
          config.trustRequirements,
        );

        if (!trustResult.permitted) {
          const decision: GovernanceDecision = {
            permitted: false,
            toolName,
            reason: trustResult.reason,
            ...(trustResult.trustLevel !== undefined
              ? { trustLevel: trustResult.trustLevel }
              : {}),
          };
          await auditDecision(engine, config.agentId, toolName, decision);

          if (config.onDenied === 'error') {
            throw new GovernanceDeniedError(decision);
          }
          return buildDenialResult(decision);
        }

        // ----------------------------------------------------------------
        // Step 2 — Budget evaluation
        // ----------------------------------------------------------------
        const budgetResult = await evaluateBudget(
          engine,
          toolName,
          config.budgetCategories,
        );

        if (!budgetResult.permitted) {
          const decision: GovernanceDecision = {
            permitted: false,
            toolName,
            reason: budgetResult.reason,
            ...(trustResult.trustLevel !== undefined
              ? { trustLevel: trustResult.trustLevel }
              : {}),
            ...(budgetResult.budgetImpact !== undefined
              ? { budgetImpact: budgetResult.budgetImpact }
              : {}),
          };
          await auditDecision(engine, config.agentId, toolName, decision);

          if (config.onDenied === 'error') {
            throw new GovernanceDeniedError(decision);
          }
          return buildDenialResult(decision);
        }

        // ----------------------------------------------------------------
        // Step 3 — Audit permit decision before forwarding
        // ----------------------------------------------------------------
        const permitDecision: GovernanceDecision = {
          permitted: true,
          toolName,
          reason: buildPermitReason(trustResult.reason, budgetResult.reason),
          ...(trustResult.trustLevel !== undefined
            ? { trustLevel: trustResult.trustLevel }
            : {}),
          ...(budgetResult.budgetImpact !== undefined
            ? { budgetImpact: budgetResult.budgetImpact }
            : {}),
        };
        await auditDecision(engine, config.agentId, toolName, permitDecision);

        // ----------------------------------------------------------------
        // Step 4 — Forward to the real server
        // ----------------------------------------------------------------
        const result = await target.callTool(toolName, args);

        // ----------------------------------------------------------------
        // Step 5 — Record budget spend after successful execution
        // ----------------------------------------------------------------
        await recordBudgetSpend(engine, toolName, config.budgetCategories);

        return result;
      };
    },
  });
}

// ---------------------------------------------------------------------------
// Internal utility
// ---------------------------------------------------------------------------

/**
 * Combine trust and budget permit reasons into a single summary string.
 * Both will often be "no requirement" messages; this surfaces a clean
 * audit reason without discarding either.
 */
function buildPermitReason(trustReason: string, budgetReason: string): string {
  if (trustReason === 'No trust requirement for this tool' &&
      budgetReason === 'No budget category for this tool') {
    return 'Permitted: no governance requirements configured for this tool';
  }
  return `Permitted — trust: ${trustReason}; budget: ${budgetReason}`;
}
