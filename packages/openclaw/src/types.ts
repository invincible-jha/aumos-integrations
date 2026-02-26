// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 MuVeraAI Corporation

// ---------------------------------------------------------------------------
// Minimal MCP server interface
//
// Deliberately avoids importing the MCP SDK so that this package has zero
// mandatory runtime dependency on any particular MCP implementation.
// Any object that satisfies MCPServer can be wrapped by this plugin.
// ---------------------------------------------------------------------------

/**
 * Minimal surface of an MCP server that this plugin needs to intercept.
 * Satisfies both the official MCP TypeScript SDK server shape and any
 * lightweight custom implementation.
 */
export interface MCPServer {
  callTool(name: string, args: unknown): Promise<MCPToolResult>;
}

/**
 * The return type of an MCP tool call.
 * Mirrors the MCP protocol response shape.
 */
export interface MCPToolResult {
  content: Array<MCPContentItem>;
  isError?: boolean;
}

/**
 * A single item in the MCP tool result content array.
 * Only the `text` type is modelled here; implementations may extend this
 * with additional types (image, resource, etc.) without breaking the plugin.
 */
export interface MCPContentItem {
  type: string;
  text: string;
}

// ---------------------------------------------------------------------------
// Governance decision types
// ---------------------------------------------------------------------------

/**
 * The resolved outcome of evaluating a tool call against governance policies.
 * Returned by both OpenClawGovernancePlugin.check() and logged after every
 * intercepted call.
 */
export interface GovernanceDecision {
  /** Whether the tool call is permitted under current governance policies. */
  readonly permitted: boolean;
  /**
   * Human-readable explanation of the decision.
   * Always present — even on permit — so callers can log meaningful context.
   */
  readonly reason: string;
  /** The MCP tool name that was evaluated. */
  readonly toolName: string;
  /**
   * Effective trust level of the agent at evaluation time.
   * Present when a trust check was performed; absent when governance is
   * configured without trust requirements.
   */
  readonly trustLevel?: number;
  /**
   * Estimated or recorded budget impact of the tool call.
   * Present when a budget check was performed; absent otherwise.
   */
  readonly budgetImpact?: number;
}

// ---------------------------------------------------------------------------
// Interceptor configuration
// ---------------------------------------------------------------------------

/**
 * Configuration passed from the plugin into the Proxy interceptor.
 * Kept separate from PluginConfig so the interceptor layer has no dependency
 * on the plugin class or Zod schemas.
 */
export interface InterceptorConfig {
  /** Agent identifier forwarded to the governance engine on every check. */
  readonly agentId: string;
  /**
   * Minimum trust level required per tool name.
   * A tool name absent from this map is permitted at any trust level.
   */
  readonly trustRequirements: Readonly<Record<string, number>>;
  /**
   * Budget category mapping per tool name.
   * Allows different tools to draw from different spending envelopes.
   */
  readonly budgetCategories: Readonly<Record<string, string>>;
  /**
   * Behaviour when a tool call is denied by governance.
   *
   * - `'error'`   — throw a GovernanceDeniedError so the caller's try/catch
   *                 fires and the error propagates up the call stack.
   * - `'message'` — return a synthetic MCPToolResult with isError: true and
   *                 a human-readable denial message in content[0].text.
   */
  readonly onDenied: 'error' | 'message';
}

// ---------------------------------------------------------------------------
// Error types
// ---------------------------------------------------------------------------

/**
 * Thrown by the interceptor when a tool call is denied and onDenied is 'error'.
 * Carries the full GovernanceDecision so callers can inspect the reason.
 */
export class GovernanceDeniedError extends Error {
  public readonly decision: GovernanceDecision;

  constructor(decision: GovernanceDecision) {
    super(
      `Governance denied tool call '${decision.toolName}': ${decision.reason}`,
    );
    this.name = 'GovernanceDeniedError';
    this.decision = decision;
  }
}
