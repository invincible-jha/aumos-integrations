// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 MuVeraAI Corporation

import { z } from 'zod';

// ---------------------------------------------------------------------------
// Zod schemas — runtime validation at the system boundary
// ---------------------------------------------------------------------------

/**
 * Zod schema for validating the trust-requirements map.
 * Keys are MCP tool names; values are integer trust levels in [0, 5].
 */
const TrustRequirementsSchema = z
  .record(z.string(), z.number().int().min(0).max(5))
  .optional()
  .default({});

/**
 * Zod schema for validating the budget-categories map.
 * Keys are MCP tool names; values are budget category identifiers.
 */
const BudgetCategoriesSchema = z
  .record(z.string(), z.string().min(1))
  .optional()
  .default({});

/**
 * Zod schema for the full plugin configuration object.
 *
 * - agentId: non-empty string identifying the agent being governed.
 * - trustRequirements: per-tool minimum trust levels (default empty — no check).
 * - budgetCategories: per-tool budget category names (default empty — no check).
 * - onDenied: denial mode, either 'error' (throw) or 'message' (safe response).
 */
export const PluginConfigSchema = z.object({
  agentId: z.string().min(1, 'agentId must be a non-empty string'),
  trustRequirements: TrustRequirementsSchema,
  budgetCategories: BudgetCategoriesSchema,
  onDenied: z.enum(['error', 'message']).optional().default('message'),
});

/**
 * Validated plugin configuration type.
 * All optional fields are resolved to concrete defaults after parsing.
 */
export type PluginConfig = z.infer<typeof PluginConfigSchema>;

/**
 * Raw input type accepted by the OpenClawGovernancePlugin constructor.
 * Optional fields may be omitted — they are filled in by Zod defaults.
 */
export type PluginConfigInput = z.input<typeof PluginConfigSchema>;

// ---------------------------------------------------------------------------
// Validation helper
// ---------------------------------------------------------------------------

/**
 * Parse and validate raw plugin config input, returning a fully-resolved
 * PluginConfig with all defaults applied.
 *
 * Throws a ZodError with descriptive field paths if validation fails.
 */
export function parsePluginConfig(input: PluginConfigInput): PluginConfig {
  return PluginConfigSchema.parse(input);
}
