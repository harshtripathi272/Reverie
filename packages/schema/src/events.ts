/**
 * Reverie CognitiveEvent schema — v1.0 (FROZEN).
 *
 * Wire format: camelCase JSON. Every event is locatable in a tree via
 * `parentId` + `depth`. New event types must be additive and bump the schema
 * version.
 *
 * Architecture note: the canonical definitions live in `./validation.ts` as
 * Zod schemas. The TypeScript types in this file are inferred from those
 * schemas, which guarantees that types and runtime validators can never drift
 * apart. Only the constants and string-union event-type list are hand-written
 * here.
 */

import type { z } from "zod";
import type {
  CognitiveEventSchema,
  ContextPayloadSchema,
  EventPayloadSchema,
  GenericPayloadSchema,
  GoalPayloadSchema,
  MemoryPayloadSchema,
  PlannerPayloadSchema,
  ReasoningPayloadSchema,
  ReflectionPayloadSchema,
  RetryPayloadSchema,
  RunCreateSchema,
  RunSchema,
  RunUpdateSchema,
  SubagentPayloadSchema,
  ToolPayloadSchema,
  ValidationPayloadSchema,
} from "./validation.js";

// -----------------------------------------------------------------------------
// Event type list (string union)
// -----------------------------------------------------------------------------

export const COGNITIVE_EVENT_TYPES = [
  "goal.created",
  "goal.completed",
  "goal.failed",
  "tool.called",
  "tool.returned",
  "tool.failed",
  "memory.retrieved",
  "memory.stored",
  "retry.triggered",
  "retry.exhausted",
  "reflection.generated",
  "subagent.spawned",
  "subagent.completed",
  "validation.passed",
  "validation.failed",
  "context.truncated",
  "planner.updated",
  "reasoning.extracted",
] as const;

export type CognitiveEventType = (typeof COGNITIVE_EVENT_TYPES)[number];

export type Priority = "critical" | "high" | "medium" | "low";
export type Severity = "error" | "warning" | "info";
export type RunStatus = "running" | "completed" | "failed" | "aborted";

// -----------------------------------------------------------------------------
// Inferred payload types — sourced from Zod schemas
// -----------------------------------------------------------------------------

export type GoalPayload = z.infer<typeof GoalPayloadSchema>;
export type ToolPayload = z.infer<typeof ToolPayloadSchema>;
export type MemoryPayload = z.infer<typeof MemoryPayloadSchema>;
export type RetryPayload = z.infer<typeof RetryPayloadSchema>;
export type ReflectionPayload = z.infer<typeof ReflectionPayloadSchema>;
export type SubagentPayload = z.infer<typeof SubagentPayloadSchema>;
export type ValidationPayload = z.infer<typeof ValidationPayloadSchema>;
export type ContextPayload = z.infer<typeof ContextPayloadSchema>;
export type ReasoningPayload = z.infer<typeof ReasoningPayloadSchema>;
export type PlannerPayload = z.infer<typeof PlannerPayloadSchema>;
export type GenericPayload = z.infer<typeof GenericPayloadSchema>;
export type EventPayload = z.infer<typeof EventPayloadSchema>;

// -----------------------------------------------------------------------------
// Inferred event + run types
// -----------------------------------------------------------------------------

export type CognitiveEvent = z.infer<typeof CognitiveEventSchema>;
export type RunCreate = z.infer<typeof RunCreateSchema>;
export type RunUpdate = z.infer<typeof RunUpdateSchema>;
export type Run = z.infer<typeof RunSchema>;

// -----------------------------------------------------------------------------
// Schema version constant — bump only on additive changes; breaking changes
// require a new major version.
// -----------------------------------------------------------------------------

export const SCHEMA_VERSION = "1.0" as const;
export type SchemaVersion = typeof SCHEMA_VERSION;
