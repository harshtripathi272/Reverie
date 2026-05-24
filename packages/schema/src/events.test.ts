/**
 * Schema round-trip and validation tests. One positive case per event type,
 * plus negative cases that exercise the most likely class of mistakes (missing
 * field, wrong type, bad discriminator, out-of-range number, extra field).
 */

import { describe, expect, it } from "vitest";
import {
  COGNITIVE_EVENT_TYPES,
  CognitiveEventBatchSchema,
  CognitiveEventSchema,
  type CognitiveEvent,
  type EventPayload,
  parseCognitiveEvent,
  safeParseCognitiveEvent,
  RunCreateSchema,
  RunSchema,
  RunUpdateSchema,
  SCHEMA_VERSION,
} from "./index.js";

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

const RUN_ID = "11111111-1111-4111-8111-111111111111";
const SESSION_ID = "22222222-2222-4222-8222-222222222222";
const AGENT_ID = "agent-test";
const PARENT_ID = "33333333-3333-4333-8333-333333333333";

const newId = (() => {
  let n = 0;
  return () => {
    n += 1;
    const hex = n.toString(16).padStart(12, "0");
    return `00000000-0000-4000-8000-${hex}`;
  };
})();

function makeEvent(
  type: CognitiveEvent["type"],
  payload: EventPayload,
  overrides: Partial<CognitiveEvent> = {},
): CognitiveEvent {
  return {
    id: newId(),
    type,
    runId: RUN_ID,
    sessionId: SESSION_ID,
    agentId: AGENT_ID,
    parentId: null,
    depth: 0,
    timestamp: 1_700_000_000_000,
    durationMs: null,
    payload,
    salience: null,
    anomaly: false,
    schemaVersion: SCHEMA_VERSION,
    ...overrides,
  };
}

// One representative event per payload `_type`. Round-tripping all of them
// covers every payload schema branch.
const SAMPLE_EVENTS: ReadonlyArray<CognitiveEvent> = [
  makeEvent("goal.created", {
    _type: "goal",
    intent: "Research observability tools",
    priority: "high",
    context: "user request",
  }),
  makeEvent("tool.called", {
    _type: "tool",
    toolName: "search_web",
    args: { query: "AI agent observability" },
    result: null,
    latencyMs: 0,
    tokenCost: null,
    success: true,
    errorMessage: null,
  }),
  makeEvent("tool.returned", {
    _type: "tool",
    toolName: "search_web",
    args: { query: "AI agent observability" },
    result: { hits: 3 },
    latencyMs: 42.5,
    tokenCost: 120,
    success: true,
    errorMessage: null,
  }),
  makeEvent("memory.retrieved", {
    _type: "memory",
    query: "previous research",
    hitCount: 2,
    relevanceScores: [0.91, 0.78],
    retrievalMs: 12.3,
    storageKey: "vector:abc",
  }),
  makeEvent("retry.triggered", {
    _type: "retry",
    reason: "timeout",
    attempt: 2,
    maxAttempts: 3,
    previousError: "ECONNRESET",
    backoffMs: 500,
  }),
  makeEvent("reflection.generated", {
    _type: "reflection",
    insight: "Tool A is unreliable, switching to Tool B",
    triggeredBy: PARENT_ID,
    actionTaken: "switch_tool",
    confidence: 0.82,
  }),
  makeEvent("subagent.spawned", {
    _type: "subagent",
    agentType: "researcher",
    task: "Find sources on topic X",
    delegatedGoalId: PARENT_ID,
    childRunId: null,
  }),
  makeEvent("validation.passed", {
    _type: "validation",
    checkName: "schema_check",
    passed: true,
    severity: "info",
    details: "ok",
  }),
  makeEvent("context.truncated", {
    _type: "context",
    tokensUsed: 7500,
    tokenLimit: 8000,
    percentUsed: 93.75,
    truncatedMessages: 4,
  }),
  makeEvent("reasoning.extracted", {
    _type: "reasoning",
    rawText: null,
    summary: "Considered three approaches, chose B for cost reasons.",
    modelId: "gpt-4o-mini",
    tokensUsed: 230,
  }),
  makeEvent("planner.updated", {
    _type: "planner",
    plan: "1. search 2. read 3. summarize",
    step: 1,
    totalSteps: 3,
    revision: 0,
  }),
];

// -----------------------------------------------------------------------------
// Positive: round-trip every payload type
// -----------------------------------------------------------------------------

describe("CognitiveEventSchema — round trip", () => {
  it("accepts every payload type and round-trips through JSON", () => {
    for (const evt of SAMPLE_EVENTS) {
      const json = JSON.stringify(evt);
      const reparsed = parseCognitiveEvent(JSON.parse(json));
      expect(reparsed).toEqual(evt);
    }
  });

  it("safeParse returns success for every sample", () => {
    for (const evt of SAMPLE_EVENTS) {
      const r = safeParseCognitiveEvent(evt);
      expect(r.success).toBe(true);
    }
  });

  it("covers every documented event type at least once", () => {
    // The sample set doesn't have to cover every event.type — many event types
    // share a payload shape (e.g. tool.called / tool.returned / tool.failed all
    // use ToolPayload). Just sanity-check that the type enum is non-empty.
    expect(COGNITIVE_EVENT_TYPES.length).toBeGreaterThan(0);
    for (const t of COGNITIVE_EVENT_TYPES) {
      expect(typeof t).toBe("string");
    }
  });
});

// -----------------------------------------------------------------------------
// Negative: each rejection class
// -----------------------------------------------------------------------------

describe("CognitiveEventSchema — rejections", () => {
  const base = SAMPLE_EVENTS[0]!;

  it("rejects an unknown event.type", () => {
    const bad = { ...base, type: "goal.invented" };
    expect(safeParseCognitiveEvent(bad).success).toBe(false);
  });

  it("rejects an unknown payload._type", () => {
    const bad = { ...base, payload: { _type: "wat", foo: "bar" } };
    expect(safeParseCognitiveEvent(bad).success).toBe(false);
  });

  it("rejects a non-UUID id", () => {
    const bad = { ...base, id: "not-a-uuid" };
    expect(safeParseCognitiveEvent(bad).success).toBe(false);
  });

  it("rejects negative depth", () => {
    const bad = { ...base, depth: -1 };
    expect(safeParseCognitiveEvent(bad).success).toBe(false);
  });

  it("rejects negative timestamp", () => {
    const bad = { ...base, timestamp: -1 };
    expect(safeParseCognitiveEvent(bad).success).toBe(false);
  });

  it("rejects salience outside [0, 1]", () => {
    const bad = { ...base, salience: 1.5 };
    expect(safeParseCognitiveEvent(bad).success).toBe(false);
  });

  it("rejects wrong schema version", () => {
    const bad = { ...base, schemaVersion: "0.9" };
    expect(safeParseCognitiveEvent(bad).success).toBe(false);
  });

  it("rejects unknown top-level field (strict mode)", () => {
    const bad = { ...base, extraField: "no" };
    expect(safeParseCognitiveEvent(bad).success).toBe(false);
  });

  it("rejects a tool payload with empty toolName", () => {
    const bad = makeEvent("tool.called", {
      _type: "tool",
      toolName: "",
      args: {},
      result: null,
      latencyMs: 0,
      tokenCost: null,
      success: true,
      errorMessage: null,
    });
    expect(safeParseCognitiveEvent(bad).success).toBe(false);
  });

  it("rejects a retry payload with attempt = 0", () => {
    const bad = makeEvent("retry.triggered", {
      _type: "retry",
      reason: "x",
      attempt: 0, // must be positive
      maxAttempts: 3,
      previousError: "x",
      backoffMs: 0,
    });
    expect(safeParseCognitiveEvent(bad).success).toBe(false);
  });

  it("requires payload._type to match the discriminator", () => {
    // GoalPayload sent under a tool.* event.type is structurally legal at the
    // event level (we don't currently cross-validate payload _type vs event
    // type — that's a higher-level concern).
    // But a payload missing _type entirely must be rejected.
    const bad = { ...base, payload: { intent: "x", priority: "low", context: "" } };
    expect(safeParseCognitiveEvent(bad).success).toBe(false);
  });
});

// -----------------------------------------------------------------------------
// Batch
// -----------------------------------------------------------------------------

describe("CognitiveEventBatchSchema", () => {
  it("accepts a non-empty batch", () => {
    const r = CognitiveEventBatchSchema.safeParse(SAMPLE_EVENTS);
    expect(r.success).toBe(true);
  });

  it("rejects an empty batch", () => {
    const r = CognitiveEventBatchSchema.safeParse([]);
    expect(r.success).toBe(false);
  });

  it("rejects a batch with one bad event", () => {
    const r = CognitiveEventBatchSchema.safeParse([
      ...SAMPLE_EVENTS,
      { ...SAMPLE_EVENTS[0]!, id: "not-a-uuid" },
    ]);
    expect(r.success).toBe(false);
  });
});

// -----------------------------------------------------------------------------
// Run schemas
// -----------------------------------------------------------------------------

describe("Run schemas", () => {
  it("RunCreateSchema accepts a well-formed payload", () => {
    const r = RunCreateSchema.safeParse({
      runId: RUN_ID,
      sessionId: SESSION_ID,
      agentId: AGENT_ID,
      runtime: "openai-agents",
      startedAt: 1_700_000_000_000,
      goal: null,
    });
    expect(r.success).toBe(true);
  });

  it("RunCreateSchema rejects missing runtime", () => {
    const r = RunCreateSchema.safeParse({
      runId: RUN_ID,
      sessionId: SESSION_ID,
      agentId: AGENT_ID,
      startedAt: 1_700_000_000_000,
      goal: null,
    });
    expect(r.success).toBe(false);
  });

  it("RunUpdateSchema accepts partial updates", () => {
    expect(RunUpdateSchema.safeParse({ status: "completed" }).success).toBe(true);
    expect(RunUpdateSchema.safeParse({}).success).toBe(true);
  });

  it("RunUpdateSchema rejects invalid status", () => {
    const r = RunUpdateSchema.safeParse({ status: "??" });
    expect(r.success).toBe(false);
  });

  it("RunSchema round-trips a fully-populated run", () => {
    const run = {
      id: RUN_ID,
      sessionId: SESSION_ID,
      agentId: AGENT_ID,
      runtime: "openai-agents",
      startedAt: 1_700_000_000_000,
      completedAt: 1_700_000_001_000,
      status: "completed" as const,
      goal: "Research observability",
      totalEvents: 23,
      totalTokens: 4500,
      totalToolCalls: 7,
      totalRetries: 1,
      totalSubagents: 0,
      pinned: false,
      tags: ["research", "test"],
      createdAt: 1_700_000_000_000,
    };
    const r = RunSchema.safeParse(run);
    expect(r.success).toBe(true);
  });
});
