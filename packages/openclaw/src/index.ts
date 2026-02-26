// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 MuVeraAI Corporation

/**
 * @aumos/openclaw-governance
 *
 * Enterprise governance plugin for OpenClaw MCP servers.
 * Depends only on @aumos/governance (public SDK) and minimal MCP-compatible types.
 *
 * Public API surface:
 * - OpenClawGovernancePlugin  — main plugin class
 * - createGovernedProxy       — lower-level Proxy factory for custom integration
 * - GovernanceDeniedError     — error thrown on denial when onDenied: 'error'
 * - Types: MCPServer, MCPToolResult, MCPContentItem, GovernanceDecision, InterceptorConfig
 * - Config: PluginConfigSchema, parsePluginConfig, PluginConfig, PluginConfigInput
 */

// Plugin class
export { OpenClawGovernancePlugin } from './plugin.js';

// Interceptor factory (lower-level escape hatch)
export { createGovernedProxy } from './interceptor.js';

// Types
export type {
  MCPServer,
  MCPToolResult,
  MCPContentItem,
  GovernanceDecision,
  InterceptorConfig,
} from './types.js';
export { GovernanceDeniedError } from './types.js';

// Configuration
export { PluginConfigSchema, parsePluginConfig } from './config.js';
export type { PluginConfig, PluginConfigInput } from './config.js';
