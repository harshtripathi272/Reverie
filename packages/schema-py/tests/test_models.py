"""Round-trip and rejection tests for ``reverie_schema``.

For every payload type:
  - construct via Python kwargs (snake_case)
  - dump to JSON (must come out as camelCase, with ``_type`` discriminator)
  - re-parse from that JSON (must equal original)

For each rejection class (bad UUID, unknown type, missing field, extra field,
out-of-range numbers, wrong discriminator), assert ``ValidationError`` is
raised.
"""

from __future__ import annotations

import json
import uuid

import pytest
from pydantic import ValidationError

from reverie_schema import (
    COGNITIVE_EVENT_TYPES,
    SCHEMA_VERSION,
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
PARENT_ID = "33333333-3333-4333-8333-333333333333"


def _new_id() -> str:
    return str(uuid.uuid4())


def _make_event(type_: str, payload, **overrides) -> CognitiveEvent:
    base = dict(
        type=type_,
        run_id=RUN_ID,
        session_id=SESSION_ID,
        agent_id="agent-test",
        parent_id=None,
        depth=0,
        timestamp=1_700_000_000_000,
        duration_ms=None,
        payload=payload,
        salience=None,
        anomaly=False,
    )
    base.update(overrides)
    return CognitiveEvent(**base)


SAMPLE_EVENTS: list[CognitiveEvent] = [
    _make_event(
        "goal.created",
        GoalPayload(intent="Research X", priority="high", context="user request"),
    ),
    _make_event(
        "tool.called",
        ToolPayload(
            tool_name="search_web",
            args={"query": "AI agent observability"},
            result=None,
            latency_ms=0.0,
            token_cost=None,
            success=True,
            error_message=None,
        ),
    ),
    _make_event(
        "tool.returned",
        ToolPayload(
            tool_name="search_web",
            args={"query": "AI agent observability"},
            result={"hits": 3},
            latency_ms=42.5,
            token_cost=120,
            success=True,
            error_message=None,
        ),
        duration_ms=42.5,
    ),
    _make_event(
        "memory.retrieved",
        MemoryPayload(
            query="prior research",
            hit_count=2,
            relevance_scores=[0.91, 0.78],
            retrieval_ms=12.3,
            storage_key="vector:abc",
        ),
    ),
    _make_event(
        "retry.triggered",
        RetryPayload(
            reason="timeout",
            attempt=2,
            max_attempts=3,
            previous_error="ECONNRESET",
            backoff_ms=500,
        ),
    ),
    _make_event(
        "reflection.generated",
        ReflectionPayload(
            insight="Tool A is unreliable",
            triggered_by=PARENT_ID,
            action_taken="switch_tool",
            confidence=0.82,
        ),
    ),
    _make_event(
        "subagent.spawned",
        SubagentPayload(
            agent_type="researcher",
            task="Find sources",
            delegated_goal_id=PARENT_ID,
            child_run_id=None,
        ),
    ),
    _make_event(
        "validation.passed",
        ValidationPayload(
            check_name="schema",
            passed=True,
            severity="info",
            details="ok",
        ),
    ),
    _make_event(
        "context.truncated",
        ContextPayload(
            tokens_used=7500,
            token_limit=8000,
            percent_used=93.75,
            truncated_messages=4,
        ),
    ),
    _make_event(
        "reasoning.extracted",
        ReasoningPayload(
            raw_text=None,
            summary="Considered three approaches.",
            model_id="gpt-4o-mini",
            tokens_used=230,
        ),
    ),
    _make_event(
        "planner.updated",
        PlannerPayload(plan="1. search 2. read", step=1, total_steps=3, revision=0),
    ),
    _make_event(
        "goal.completed",
        GenericPayload(data={"note": "fallback path"}),
    ),
]


# ---------------------------------------------------------------------------
# Positive: round-trip every payload type
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_every_sample_round_trips_through_json(self):
        for evt in SAMPLE_EVENTS:
            blob = evt.model_dump_json()
            restored = CognitiveEvent.model_validate_json(blob)
            assert restored == evt

    def test_wire_format_uses_camelcase(self):
        evt = SAMPLE_EVENTS[0]
        wire = json.loads(evt.model_dump_json())
        # Top-level fields are camelCase.
        for key in (
            "id",
            "type",
            "runId",
            "sessionId",
            "agentId",
            "parentId",
            "depth",
            "timestamp",
            "durationMs",
            "payload",
            "salience",
            "anomaly",
            "schemaVersion",
        ):
            assert key in wire, f"missing wire key: {key}"
        # Snake-case forms must NOT appear on the wire.
        for forbidden in ("run_id", "session_id", "parent_id", "schema_version"):
            assert forbidden not in wire

    def test_payload_uses_underscore_type_discriminator(self):
        evt = _make_event(
            "tool.called",
            ToolPayload(
                tool_name="x",
                args={},
                result=None,
                latency_ms=0,
                token_cost=None,
                success=True,
                error_message=None,
            ),
        )
        wire = json.loads(evt.model_dump_json())
        assert wire["payload"]["_type"] == "tool"
        assert wire["payload"]["toolName"] == "x"
        assert "tool_name" not in wire["payload"]
        assert "kind" not in wire["payload"]

    def test_can_construct_from_camelcase_json(self):
        # Parsing a wire-format JSON (camelCase) must work.
        wire = {
            "id": "00000000-0000-4000-8000-000000000001",
            "type": "goal.created",
            "runId": RUN_ID,
            "sessionId": SESSION_ID,
            "agentId": "agent-test",
            "parentId": None,
            "depth": 0,
            "timestamp": 1_700_000_000_000,
            "durationMs": None,
            "payload": {
                "_type": "goal",
                "intent": "x",
                "priority": "high",
                "context": "",
            },
            "salience": None,
            "anomaly": False,
            "schemaVersion": SCHEMA_VERSION,
        }
        evt = CognitiveEvent.model_validate(wire)
        assert evt.run_id == RUN_ID
        assert evt.payload.kind == "goal"

    def test_schema_version_is_pinned(self):
        assert SCHEMA_VERSION == "1.0"
        for evt in SAMPLE_EVENTS:
            assert evt.schema_version == "1.0"

    def test_event_type_enum_matches_typescript(self):
        # The same ordering and contents as the TS COGNITIVE_EVENT_TYPES.
        # If this drifts, both languages must be updated together.
        expected = (
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
        )
        assert COGNITIVE_EVENT_TYPES == expected


# ---------------------------------------------------------------------------
# Negative: each rejection class
# ---------------------------------------------------------------------------


class TestRejections:
    def _good(self) -> dict:
        return json.loads(SAMPLE_EVENTS[0].model_dump_json())

    def test_rejects_unknown_event_type(self):
        bad = self._good()
        bad["type"] = "goal.invented"
        with pytest.raises(ValidationError):
            CognitiveEvent.model_validate(bad)

    def test_rejects_unknown_payload_type(self):
        bad = self._good()
        bad["payload"] = {"_type": "wat", "foo": "bar"}
        with pytest.raises(ValidationError):
            CognitiveEvent.model_validate(bad)

    def test_rejects_non_uuid_id(self):
        bad = self._good()
        bad["id"] = "not-a-uuid"
        with pytest.raises(ValidationError):
            CognitiveEvent.model_validate(bad)

    def test_rejects_negative_depth(self):
        bad = self._good()
        bad["depth"] = -1
        with pytest.raises(ValidationError):
            CognitiveEvent.model_validate(bad)

    def test_rejects_negative_timestamp(self):
        bad = self._good()
        bad["timestamp"] = -1
        with pytest.raises(ValidationError):
            CognitiveEvent.model_validate(bad)

    def test_rejects_salience_above_one(self):
        bad = self._good()
        bad["salience"] = 1.5
        with pytest.raises(ValidationError):
            CognitiveEvent.model_validate(bad)

    def test_rejects_wrong_schema_version(self):
        bad = self._good()
        bad["schemaVersion"] = "0.9"
        with pytest.raises(ValidationError):
            CognitiveEvent.model_validate(bad)

    def test_rejects_unknown_top_level_field(self):
        bad = self._good()
        bad["extraField"] = "no"
        with pytest.raises(ValidationError):
            CognitiveEvent.model_validate(bad)

    def test_rejects_empty_tool_name(self):
        with pytest.raises(ValidationError):
            ToolPayload(
                tool_name="",
                args={},
                result=None,
                latency_ms=0,
                token_cost=None,
                success=True,
                error_message=None,
            )

    def test_rejects_retry_attempt_zero(self):
        with pytest.raises(ValidationError):
            RetryPayload(
                reason="x",
                attempt=0,
                max_attempts=3,
                previous_error="x",
                backoff_ms=0,
            )

    def test_rejects_payload_without_discriminator(self):
        bad = self._good()
        bad["payload"] = {"intent": "x", "priority": "low", "context": ""}
        with pytest.raises(ValidationError):
            CognitiveEvent.model_validate(bad)

    def test_rejects_negative_latency(self):
        with pytest.raises(ValidationError):
            ToolPayload(
                tool_name="x",
                args={},
                result=None,
                latency_ms=-1.0,
                token_cost=None,
                success=True,
                error_message=None,
            )

    def test_rejects_confidence_above_one(self):
        with pytest.raises(ValidationError):
            ReflectionPayload(
                insight="i",
                triggered_by=PARENT_ID,
                action_taken="a",
                confidence=1.5,
            )


# ---------------------------------------------------------------------------
# Run schemas
# ---------------------------------------------------------------------------


class TestRunSchemas:
    def test_run_create_round_trips(self):
        rc = RunCreate(
            run_id=RUN_ID,
            session_id=SESSION_ID,
            agent_id="agent-test",
            runtime="openai-agents",
            started_at=1_700_000_000_000,
            goal=None,
        )
        wire = json.loads(rc.model_dump_json())
        assert wire["runId"] == RUN_ID
        assert wire["startedAt"] == 1_700_000_000_000
        assert RunCreate.model_validate(wire) == rc

    def test_run_create_rejects_missing_runtime(self):
        with pytest.raises(ValidationError):
            RunCreate.model_validate(
                {
                    "runId": RUN_ID,
                    "sessionId": SESSION_ID,
                    "agentId": "agent-test",
                    "startedAt": 1_700_000_000_000,
                    "goal": None,
                }
            )

    def test_run_update_accepts_partial(self):
        ru = RunUpdate.model_validate({"status": "completed"})
        assert ru.status == "completed"
        empty = RunUpdate.model_validate({})
        assert empty.status is None

    def test_run_update_rejects_invalid_status(self):
        with pytest.raises(ValidationError):
            RunUpdate.model_validate({"status": "??"})

    def test_run_round_trips(self):
        run = Run(
            id=RUN_ID,
            session_id=SESSION_ID,
            agent_id="agent-test",
            runtime="openai-agents",
            started_at=1_700_000_000_000,
            completed_at=1_700_000_001_000,
            status="completed",
            goal="Research observability",
            total_events=23,
            total_tokens=4500,
            total_tool_calls=7,
            total_retries=1,
            total_subagents=0,
            pinned=False,
            tags=["research", "test"],
            created_at=1_700_000_000_000,
        )
        wire = json.loads(run.model_dump_json())
        assert wire["totalToolCalls"] == 7
        assert Run.model_validate(wire) == run
