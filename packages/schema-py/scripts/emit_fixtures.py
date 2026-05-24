"""Emit a fixture file containing one valid CognitiveEvent of every payload
type, in wire format. The TypeScript schema test reads this file and verifies
that every event passes ``CognitiveEventSchema.parse``.

This is the cross-language conformance guarantee.

Run from the repo root:

    .venv/Scripts/python.exe packages/schema-py/scripts/emit_fixtures.py
"""

from __future__ import annotations

import json
from pathlib import Path

from reverie_schema import (
    CognitiveEvent,
    ContextPayload,
    GenericPayload,
    GoalPayload,
    MemoryPayload,
    PlannerPayload,
    ReasoningPayload,
    ReflectionPayload,
    RetryPayload,
    Run,
    RunCreate,
    RunUpdate,
    SubagentPayload,
    ToolPayload,
    ValidationPayload,
)

RUN_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
PARENT_ID = "33333333-3333-4333-8333-333333333333"


def _evt(idx: int, type_: str, payload, **overrides) -> CognitiveEvent:
    base = dict(
        id=f"00000000-0000-4000-8000-{idx:012x}",
        type=type_,
        run_id=RUN_ID,
        session_id=SESSION_ID,
        agent_id="agent-fixture",
        parent_id=None,
        depth=0,
        timestamp=1_700_000_000_000 + idx,
        duration_ms=None,
        payload=payload,
        salience=None,
        anomaly=False,
    )
    base.update(overrides)
    return CognitiveEvent(**base)


def build_events() -> list[CognitiveEvent]:
    return [
        _evt(1, "goal.created", GoalPayload(intent="Research X", priority="high", context="ctx")),
        _evt(
            2,
            "tool.called",
            ToolPayload(
                tool_name="search_web",
                args={"query": "x"},
                result=None,
                latency_ms=0,
                token_cost=None,
                success=True,
                error_message=None,
            ),
        ),
        _evt(
            3,
            "tool.returned",
            ToolPayload(
                tool_name="search_web",
                args={"query": "x"},
                result={"hits": 3},
                latency_ms=42.5,
                token_cost=120,
                success=True,
                error_message=None,
            ),
            duration_ms=42.5,
        ),
        _evt(
            4,
            "memory.retrieved",
            MemoryPayload(
                query="prior",
                hit_count=2,
                relevance_scores=[0.9, 0.8],
                retrieval_ms=12.3,
                storage_key="vec:1",
            ),
        ),
        _evt(
            5,
            "retry.triggered",
            RetryPayload(
                reason="timeout",
                attempt=2,
                max_attempts=3,
                previous_error="ECONNRESET",
                backoff_ms=500,
            ),
        ),
        _evt(
            6,
            "reflection.generated",
            ReflectionPayload(
                insight="i", triggered_by=PARENT_ID, action_taken="a", confidence=0.7
            ),
        ),
        _evt(
            7,
            "subagent.spawned",
            SubagentPayload(
                agent_type="research",
                task="t",
                delegated_goal_id=PARENT_ID,
                child_run_id=None,
            ),
        ),
        _evt(
            8,
            "validation.passed",
            ValidationPayload(check_name="c", passed=True, severity="info", details="ok"),
        ),
        _evt(
            9,
            "context.truncated",
            ContextPayload(
                tokens_used=7500,
                token_limit=8000,
                percent_used=93.75,
                truncated_messages=4,
            ),
        ),
        _evt(
            10,
            "reasoning.extracted",
            ReasoningPayload(
                raw_text=None,
                summary="s",
                model_id="gpt-4o-mini",
                tokens_used=230,
            ),
        ),
        _evt(
            11,
            "planner.updated",
            PlannerPayload(plan="p", step=1, total_steps=3, revision=0),
        ),
        _evt(
            12,
            "goal.completed",
            GenericPayload(data={"note": "fallback"}),
            salience=0.42,
            anomaly=True,
        ),
    ]


def build_run() -> Run:
    return Run(
        id=RUN_ID,
        session_id=SESSION_ID,
        agent_id="agent-fixture",
        runtime="openai-agents",
        started_at=1_700_000_000_000,
        completed_at=1_700_000_001_000,
        status="completed",
        goal="Research observability",
        total_events=12,
        total_tokens=4500,
        total_tool_calls=3,
        total_retries=1,
        total_subagents=1,
        pinned=False,
        tags=["research"],
        created_at=1_700_000_000_000,
    )


def build_run_create() -> RunCreate:
    return RunCreate(
        run_id=RUN_ID,
        session_id=SESSION_ID,
        agent_id="agent-fixture",
        runtime="openai-agents",
        started_at=1_700_000_000_000,
        goal="Research observability",
    )


def build_run_update() -> RunUpdate:
    return RunUpdate(status="completed", completed_at=1_700_000_001_000)


def main() -> None:
    here = Path(__file__).resolve()
    repo_root = here.parents[3]
    out_dir = repo_root / "packages" / "schema" / "test-fixtures"
    out_dir.mkdir(parents=True, exist_ok=True)

    events = build_events()
    fixture = {
        "schemaVersion": "1.0",
        "generatedBy": "reverie-schema (Python)",
        "events": [json.loads(e.model_dump_json()) for e in events],
        "run": json.loads(build_run().model_dump_json()),
        "runCreate": json.loads(build_run_create().model_dump_json()),
        # RunUpdate is a PATCH body: only explicitly-set fields cross the wire.
        # ``exclude_unset=True`` is the source of that semantic.
        "runUpdate": json.loads(
            build_run_update().model_dump_json(exclude_unset=True)
        ),
    }
    (out_dir / "python_emitted.json").write_text(
        json.dumps(fixture, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"wrote {out_dir / 'python_emitted.json'} ({len(events)} events)")


if __name__ == "__main__":
    main()
