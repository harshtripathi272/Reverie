"""Mapper tests — span/trace → CognitiveEvent translation."""

from __future__ import annotations

import pytest
from reverie_schema import (
    CognitiveEvent,
    GenericPayload,
    GoalPayload,
    ReasoningPayload,
    SubagentPayload,
    ToolPayload,
    ValidationPayload,
)

from reverie_openai.idmap import to_end_uuid, to_uuid
from reverie_openai.mapper import (
    map_span_end,
    map_span_start,
    trace_run_id,
    trace_session_id,
    trace_workflow_name,
)

from _helpers import (
    agent_span_data,
    custom_span_data,
    function_span_data,
    generation_span_data,
    guardrail_span_data,
    handoff_span_data,
    make_span,
    make_trace,
    response_span_data,
)


# ---------------------------------------------------------------------------
# Trace helpers
# ---------------------------------------------------------------------------


class TestTraceMapping:
    def test_trace_run_id_is_uuid_v4(self):
        t = make_trace(trace_id="trace_abc123")
        run_id = trace_run_id(t)
        assert run_id == to_uuid("trace_abc123")

    def test_trace_session_id_prefers_group_id(self):
        t = make_trace(trace_id="trace_xyz", group_id="my-session")
        assert trace_session_id(t) == "my-session"

    def test_trace_session_id_falls_back_to_trace_id(self):
        t = make_trace(trace_id="trace_xyz", group_id=None)
        assert trace_session_id(t) == "trace_xyz"

    def test_trace_workflow_name(self):
        t = make_trace(name="Customer support")
        assert trace_workflow_name(t) == "Customer support"


# ---------------------------------------------------------------------------
# Span starts
# ---------------------------------------------------------------------------


class TestMapSpanStart:
    def test_agent_span_emits_goal_created(self):
        span = make_span(agent_span_data(name="planner"))
        evt = map_span_start(span, session_id="sess", agent_id="a", depth=0)
        assert isinstance(evt, CognitiveEvent)
        assert evt.type == "goal.created"
        assert isinstance(evt.payload, GoalPayload)
        assert evt.payload.intent == "planner"
        assert evt.run_id == to_uuid(span.trace_id)
        assert evt.parent_id is None
        assert evt.depth == 0

    def test_function_span_emits_tool_called(self):
        span = make_span(function_span_data(name="search_web", input='{"q":"x"}'))
        evt = map_span_start(span, session_id="sess", agent_id="a", depth=1)
        assert evt.type == "tool.called"
        assert isinstance(evt.payload, ToolPayload)
        assert evt.payload.tool_name == "search_web"
        assert evt.payload.success is True
        assert evt.payload.result is None
        assert evt.depth == 1

    def test_handoff_span_emits_subagent_spawned(self):
        span = make_span(
            handoff_span_data(from_agent="router", to_agent="research"),
            parent_id="span_parent01000000000000",
        )
        evt = map_span_start(span, session_id="sess", agent_id="a", depth=2)
        assert evt.type == "subagent.spawned"
        assert isinstance(evt.payload, SubagentPayload)
        assert evt.payload.agent_type == "research"
        assert evt.payload.delegated_goal_id == to_uuid("span_parent01000000000000")
        assert evt.parent_id == to_uuid("span_parent01000000000000")

    def test_generation_span_returns_none_on_start(self):
        span = make_span(generation_span_data())
        assert map_span_start(span, session_id="s", agent_id="a", depth=0) is None

    def test_response_span_returns_none_on_start(self):
        span = make_span(response_span_data())
        assert map_span_start(span, session_id="s", agent_id="a", depth=0) is None

    def test_guardrail_span_returns_none_on_start(self):
        span = make_span(guardrail_span_data())
        assert map_span_start(span, session_id="s", agent_id="a", depth=0) is None

    def test_custom_span_emits_planner_updated_with_generic_payload(self):
        span = make_span(custom_span_data(name="db"))
        evt = map_span_start(span, session_id="s", agent_id="a", depth=0)
        assert evt.type == "planner.updated"
        assert isinstance(evt.payload, GenericPayload)
        assert evt.payload.data["sdk_span_type"] == "custom"
        assert evt.payload.data["stage"] == "start"


# ---------------------------------------------------------------------------
# Span ends
# ---------------------------------------------------------------------------


class TestMapSpanEnd:
    def test_agent_completion(self):
        span = make_span(agent_span_data(name="planner"))
        evt = map_span_end(span, session_id="s", agent_id="a", depth=0)
        assert evt.type == "goal.completed"
        assert evt.id == to_end_uuid(span.span_id)
        # Same parent as the start event — start/end are siblings.
        assert evt.parent_id is None
        assert evt.duration_ms == 500.0  # 12:00:00.000 → 12:00:00.500

    def test_agent_failure(self):
        span = make_span(
            agent_span_data(),
            error={"message": "tool timeout", "data": None},
        )
        evt = map_span_end(span, session_id="s", agent_id="a", depth=0)
        assert evt.type == "goal.failed"
        assert isinstance(evt.payload, GoalPayload)
        assert "tool timeout" in evt.payload.context

    def test_function_returned(self):
        span = make_span(function_span_data(name="x", output={"hits": 3}))
        evt = map_span_end(span, session_id="s", agent_id="a", depth=1)
        assert evt.type == "tool.returned"
        assert isinstance(evt.payload, ToolPayload)
        assert evt.payload.success is True
        assert evt.payload.latency_ms == 500.0

    def test_function_failed(self):
        span = make_span(
            function_span_data(name="x"),
            error={"message": "404 not found", "data": None},
        )
        evt = map_span_end(span, session_id="s", agent_id="a", depth=1)
        assert evt.type == "tool.failed"
        assert isinstance(evt.payload, ToolPayload)
        assert evt.payload.success is False
        assert evt.payload.error_message == "404 not found"

    def test_handoff_completion(self):
        span = make_span(handoff_span_data())
        evt = map_span_end(span, session_id="s", agent_id="a", depth=2)
        assert evt.type == "subagent.completed"
        assert isinstance(evt.payload, SubagentPayload)

    def test_generation_emits_reasoning_extracted(self):
        span = make_span(generation_span_data(model="gpt-4o-mini", tokens=200))
        evt = map_span_end(span, session_id="s", agent_id="a", depth=2)
        assert evt.type == "reasoning.extracted"
        assert isinstance(evt.payload, ReasoningPayload)
        assert evt.payload.model_id == "gpt-4o-mini"
        assert evt.payload.tokens_used == 200
        assert evt.payload.summary == "hello!"
        assert evt.payload.raw_text is None  # we never store raw CoT

    def test_response_emits_reasoning_extracted_without_summary(self):
        span = make_span(response_span_data())
        evt = map_span_end(span, session_id="s", agent_id="a", depth=2)
        assert evt.type == "reasoning.extracted"
        assert isinstance(evt.payload, ReasoningPayload)
        assert evt.payload.tokens_used == 50

    def test_guardrail_passed(self):
        span = make_span(guardrail_span_data(triggered=False))
        evt = map_span_end(span, session_id="s", agent_id="a", depth=1)
        assert evt.type == "validation.passed"
        assert isinstance(evt.payload, ValidationPayload)
        assert evt.payload.passed is True

    def test_guardrail_triggered(self):
        span = make_span(guardrail_span_data(triggered=True))
        evt = map_span_end(span, session_id="s", agent_id="a", depth=1)
        assert evt.type == "validation.failed"
        assert isinstance(evt.payload, ValidationPayload)
        assert evt.payload.passed is False
        assert evt.payload.severity == "error"

    def test_unknown_dates_use_now(self):
        span = make_span(agent_span_data(), started_at=None, ended_at=None)
        evt = map_span_end(span, session_id="s", agent_id="a", depth=0)
        assert evt.timestamp > 0
        # No duration when we can't compute it.
        assert evt.duration_ms is None


# ---------------------------------------------------------------------------
# Cross-stage invariants
# ---------------------------------------------------------------------------


class TestStartEndPairing:
    def test_start_and_end_have_distinct_ids_but_same_parent(self):
        span = make_span(
            agent_span_data(),
            span_id="span_aaaaaaaaaaaaaaaaaaaaaa01",
            parent_id="span_bbbbbbbbbbbbbbbbbbbbbb02",
        )
        start = map_span_start(span, session_id="s", agent_id="a", depth=1)
        end = map_span_end(span, session_id="s", agent_id="a", depth=1)
        assert start.id != end.id
        assert start.parent_id == end.parent_id
        assert start.run_id == end.run_id

    def test_event_passes_full_schema_validation(self):
        # Round-tripping through model_dump_json + model_validate is the same
        # surface adversarial input would hit on the wire.
        import json

        span = make_span(function_span_data(name="search_web", output={"hits": 3}))
        for evt in (
            map_span_start(span, session_id="s", agent_id="a", depth=0),
            map_span_end(span, session_id="s", agent_id="a", depth=0),
        ):
            assert evt is not None
            blob = evt.model_dump_json()
            CognitiveEvent.model_validate(json.loads(blob))


# ---------------------------------------------------------------------------
# Defensive behaviour
# ---------------------------------------------------------------------------


class TestDefensiveDecoding:
    @pytest.mark.parametrize(
        "iso",
        [
            "2025-01-01T12:00:00Z",
            "2025-01-01T12:00:00.123Z",
            "2025-01-01T12:00:00+00:00",
            "2025-01-01T12:00:00.123+00:00",
        ],
    )
    def test_iso_variants_parse(self, iso):
        span = make_span(agent_span_data(), started_at=iso, ended_at=iso)
        evt = map_span_end(span, session_id="s", agent_id="a", depth=0)
        assert evt.timestamp > 0
