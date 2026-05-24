/**
 * Zod validators for the Reverie CognitiveEvent schema (v1.0).
 *
 * These schemas are the canonical definition of the wire format. The
 * TypeScript types in `./events.ts` are inferred from them.
 *
 * Every event entering the API or leaving an adapter MUST pass through one of
 * these schemas.
 */

import { z } from "zod";
import {
  COGNITIVE_EVENT_TYPES,
  SCHEMA_VERSION,
  type CognitiveEventType,
} from "./events.js";

// -----------------------------------------------------------------------------
// Primitives
// -----------------------------------------------------------------------------

/**
 * RFC 4122 UUID (any version). Adapters should emit v4, but we accept any
 * valid UUID for forward-compat with v7 (time-ordered) once it stabilizes.
 */
const UuidSchema = z.string().uuid();

const PrioritySchema = z.enum(["critical", "high", "medium", "low"]);
const SeveritySchema = z.enum(["error", "warning", "info"]);
const RunStatusSchema = z.enum(["running", "completed", "failed", "aborted"]);

const CognitiveEventTypeSchema = z.enum(COGNITIVE_EVENT_TYPES) satisfies z.ZodType<
  CognitiveEventType,
  z.ZodEnumDef,
  CognitiveEventType
>;

/**
 * Arbitrary JSON-compatible value, including null. Required (not optional) at
 * its position. Wrapping in `z.union([..., z.null()])` rather than `.nullable()`
 * avoids the `z.unknown()` + `.nullable()` quirk that produces an optional
 * inferred type.
 */
const JsonValueOrNullSchema = z.union([
  z.null(),
  z.string(),
  z.number(),
  z.boolean(),
  z.array(z.unknown()),
  z.record(z.unknown()),
]);

// -----------------------------------------------------------------------------
// Payload schemas — discriminated by `_type`
// -----------------------------------------------------------------------------

export const GoalPayloadSchema = z
  .object({
    _type: z.literal("goal"),
    intent: z.string(),
    priority: PrioritySchema,
    context: z.string(),
  })
  .strict();

export const ToolPayloadSchema = z
  .object({
    _type: z.literal("tool"),
    toolName: z.string().min(1),
    args: z.record(z.unknown()),
    /**
     * Result of the tool call. `null` while the call is in flight, populated
     * on completion. Strict-mode object means clients must always send the
     * field even if null.
     */
    result: JsonValueOrNullSchema,
    latencyMs: z.number().nonnegative(),
    tokenCost: z.number().int().nonnegative().nullable(),
    success: z.boolean(),
    errorMessage: z.string().nullable(),
  })
  .strict();

export const MemoryPayloadSchema = z
  .object({
    _type: z.literal("memory"),
    query: z.string(),
    hitCount: z.number().int().nonnegative(),
    relevanceScores: z.array(z.number()),
    retrievalMs: z.number().nonnegative(),
    storageKey: z.string().nullable(),
  })
  .strict();

export const RetryPayloadSchema = z
  .object({
    _type: z.literal("retry"),
    reason: z.string(),
    attempt: z.number().int().positive(),
    maxAttempts: z.number().int().positive(),
    previousError: z.string(),
    backoffMs: z.number().nonnegative(),
  })
  .strict();

export const ReflectionPayloadSchema = z
  .object({
    _type: z.literal("reflection"),
    insight: z.string(),
    triggeredBy: z.string(),
    actionTaken: z.string(),
    confidence: z.number().min(0).max(1).nullable(),
  })
  .strict();

export const SubagentPayloadSchema = z
  .object({
    _type: z.literal("subagent"),
    agentType: z.string(),
    task: z.string(),
    delegatedGoalId: z.string().nullable(),
    childRunId: z.string().nullable(),
  })
  .strict();

export const ValidationPayloadSchema = z
  .object({
    _type: z.literal("validation"),
    checkName: z.string(),
    passed: z.boolean(),
    severity: SeveritySchema,
    details: z.string(),
  })
  .strict();

export const ContextPayloadSchema = z
  .object({
    _type: z.literal("context"),
    tokensUsed: z.number().int().nonnegative(),
    tokenLimit: z.number().int().positive(),
    percentUsed: z.number().min(0).max(100),
    truncatedMessages: z.number().int().nonnegative(),
  })
  .strict();

export const ReasoningPayloadSchema = z
  .object({
    _type: z.literal("reasoning"),
    rawText: z.string().nullable(),
    summary: z.string().nullable(),
    modelId: z.string(),
    tokensUsed: z.number().int().nonnegative().nullable(),
  })
  .strict();

export const PlannerPayloadSchema = z
  .object({
    _type: z.literal("planner"),
    plan: z.string(),
    step: z.number().int().nonnegative(),
    totalSteps: z.number().int().positive().nullable(),
    revision: z.number().int().nonnegative(),
  })
  .strict();

export const GenericPayloadSchema = z
  .object({
    _type: z.literal("generic"),
    data: z.record(z.unknown()),
  })
  .strict();

export const EventPayloadSchema = z.discriminatedUnion("_type", [
  GoalPayloadSchema,
  ToolPayloadSchema,
  MemoryPayloadSchema,
  RetryPayloadSchema,
  ReflectionPayloadSchema,
  SubagentPayloadSchema,
  ValidationPayloadSchema,
  ContextPayloadSchema,
  ReasoningPayloadSchema,
  PlannerPayloadSchema,
  GenericPayloadSchema,
]);

// -----------------------------------------------------------------------------
// CognitiveEvent
// -----------------------------------------------------------------------------

export const CognitiveEventSchema = z
  .object({
    id: UuidSchema,
    type: CognitiveEventTypeSchema,
    runId: z.string().min(1),
    sessionId: z.string().min(1),
    agentId: z.string().min(1),

    parentId: z.string().nullable(),
    depth: z.number().int().nonnegative(),

    timestamp: z.number().int().nonnegative(),
    durationMs: z.number().nonnegative().nullable(),

    payload: EventPayloadSchema,

    salience: z.number().min(0).max(1).nullable(),
    anomaly: z.boolean(),

    schemaVersion: z.literal(SCHEMA_VERSION),
  })
  .strict();

/**
 * Parse and validate a `CognitiveEvent`. Throws `ZodError` on failure.
 * Use this at every trust boundary (network ingress, adapter egress, DB
 * deserialization).
 */
export function parseCognitiveEvent(input: unknown) {
  return CognitiveEventSchema.parse(input);
}

/**
 * Result-style variant — never throws. Use when you want to inspect failures
 * without a try/catch.
 */
export function safeParseCognitiveEvent(input: unknown) {
  return CognitiveEventSchema.safeParse(input);
}

// -----------------------------------------------------------------------------
// Batch
// -----------------------------------------------------------------------------

export const MAX_BATCH_SIZE = 1000;

export const CognitiveEventBatchSchema = z
  .array(CognitiveEventSchema)
  .min(1)
  .max(MAX_BATCH_SIZE);

export type CognitiveEventBatch = z.infer<typeof CognitiveEventBatchSchema>;

// -----------------------------------------------------------------------------
// Run schemas
// -----------------------------------------------------------------------------

export const RunCreateSchema = z
  .object({
    runId: z.string().min(1),
    sessionId: z.string().min(1),
    agentId: z.string().min(1),
    runtime: z.string().min(1),
    startedAt: z.number().int().nonnegative(),
    goal: z.string().nullable(),
  })
  .strict();

export const RunUpdateSchema = z
  .object({
    status: RunStatusSchema.optional(),
    completedAt: z.number().int().nonnegative().optional(),
    goal: z.string().optional(),
  })
  .strict();

export const RunSchema = z
  .object({
    id: z.string().min(1),
    sessionId: z.string().min(1),
    agentId: z.string().min(1),
    runtime: z.string().min(1),
    startedAt: z.number().int().nonnegative(),
    completedAt: z.number().int().nonnegative().nullable(),
    status: RunStatusSchema,
    goal: z.string().nullable(),
    totalEvents: z.number().int().nonnegative(),
    totalTokens: z.number().int().nonnegative(),
    totalToolCalls: z.number().int().nonnegative(),
    totalRetries: z.number().int().nonnegative(),
    totalSubagents: z.number().int().nonnegative(),
    pinned: z.boolean(),
    tags: z.array(z.string()),
    createdAt: z.number().int().nonnegative(),
  })
  .strict();
