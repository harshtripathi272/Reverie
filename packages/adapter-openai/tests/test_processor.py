"""Processor tests — verifies the SDK→emitter wiring without real HTTP.

We pass a fake emitter so we can assert the exact sequence of calls produced
by a span lifecycle.
"""

from __future__ import annotations

from typing import Any

import pytest
from reverie_schema import CognitiveEvent

from reverie_openai.config import AdapterConfig
from reverie_openai.processor import ReverieTracingProcessor

from _helpers import (
    agent_span_data,
    function_span_data,
    make_span,
    make_trace,
)


class _FakeEmitter:
    """Captures every emitter call without doing any I/O."""

    def __init__(self) -> None:
        self.events: list[CognitiveEvent] = []
        self.run_creates: list[dict] = []
        self.run_updates: list[tuple[str, dict]] = []
        self.flushed = 0
        self.shutdowns = 0

    def emit(self, event):
        self.events.append(event)

    def create_run(self, payload):
        self.run_creates.append(payload)

    def update_run(self, run_id, payload):
        self.run_updates.append((run_id, payload))

    def flush(self):
        self.flushed += 1

    def shutdown(self):
        self.shutdowns += 1


@pytest.fixture
def fake_emitter() -> _FakeEmitter:
    return _FakeEmitter()


@pytest.fixture
def config() -> AdapterConfig:
    return AdapterConfig(disabled=False, agent_id="agent-test")


@pytest.fixture
def processor(fake_emitter, config) -> ReverieTracingProcessor:
    return ReverieTracingProcessor(emitter=fake_emitter, config=config)


# ---------------------------------------------------------------------------
# Trace lifecycle
# ---------------------------------------------------------------------------


class TestTraceLifecycle:
    def test_on_trace_start_calls_create_run(self, processor, fake_emitter):
        trace = make_trace(name="research", trace_id="trace_t1" + "0" * 26, group_id="sess-x")
        processor.on_trace_start(trace)

        assert len(fake_emitter.run_creates) == 1
        payload = fake_emitter.run_creates[0]
        assert payload["sessionId"] == "sess-x"
        assert payload["agentId"] == "agent-test"
        assert payload["runtime"] == "openai-agents"
        assert payload["goal"] == "research"
        # runId is the deterministic UUID projection of the trace id.
        from reverie_openai.idmap import to_uuid
        assert payload["runId"] == to_uuid(trace.trace_id)

    def test_on_trace_end_calls_update_run(self, processor, fake_emitter):
        trace = make_trace(trace_id="trace_t2" + "0" * 26)
        processor.on_trace_start(trace)
        processor.on_trace_end(trace)

        assert len(fake_emitter.run_updates) == 1
        rid, payload = fake_emitter.run_updates[0]
        assert payload["status"] == "completed"
        assert "completedAt" in payload

    def test_on_trace_end_without_start_is_noop(self, processor, fake_emitter):
        trace = make_trace(trace_id="trace_t3" + "0" * 26)
        processor.on_trace_end(trace)
        assert fake_emitter.run_updates == []


# ---------------------------------------------------------------------------
# Span lifecycle
# ---------------------------------------------------------------------------


class TestSpanLifecycle:
    def test_span_outside_trace_is_skipped(self, processor, fake_emitter):
        # No on_trace_start called — span should be dropped.
        span = make_span(agent_span_data())
        processor.on_span_start(span)
        processor.on_span_end(span)
        assert fake_emitter.events == []

    def test_full_agent_span_emits_start_and_end(self, processor, fake_emitter):
        trace = make_trace(trace_id="trace_t4" + "0" * 26)
        processor.on_trace_start(trace)
        span = make_span(
            agent_span_data(name="planner"),
            trace_id=trace.trace_id,
            span_id="span_t4_root00000000000000",
        )
        processor.on_span_start(span)
        processor.on_span_end(span)

        assert len(fake_emitter.events) == 2
        start, end = fake_emitter.events
        assert start.type == "goal.created"
        assert end.type == "goal.completed"
        # Same parent (None — this is the root span under the trace).
        assert start.parent_id is None
        assert end.parent_id is None
        # Distinct ids.
        assert start.id != end.id


# ---------------------------------------------------------------------------
# Depth tracking
# ---------------------------------------------------------------------------


class TestDepthTracking:
    def test_depth_increases_with_nesting(self, processor, fake_emitter):
        trace = make_trace(trace_id="trace_t5" + "0" * 26)
        processor.on_trace_start(trace)

        root = make_span(
            agent_span_data(name="root"),
            trace_id=trace.trace_id,
            span_id="span_root0000000000000000",
            parent_id=None,
        )
        child = make_span(
            function_span_data(name="search"),
            trace_id=trace.trace_id,
            span_id="span_child000000000000000",
            parent_id=root.span_id,
        )
        grandchild = make_span(
            function_span_data(name="parse"),
            trace_id=trace.trace_id,
            span_id="span_grand000000000000000",
            parent_id=child.span_id,
        )

        for s in (root, child, grandchild):
            processor.on_span_start(s)

        depths_by_intent: dict[str, int] = {}
        for evt in fake_emitter.events:
            if evt.type == "goal.created":
                depths_by_intent["root"] = evt.depth
            elif evt.type == "tool.called":
                # First tool.called is "search" (child), then "parse" (grand).
                key = "search" if "search" not in depths_by_intent else "parse"
                depths_by_intent[key] = evt.depth

        assert depths_by_intent["root"] == 0
        assert depths_by_intent["search"] == 1
        assert depths_by_intent["parse"] == 2

    def test_end_event_uses_same_depth_as_start(self, processor, fake_emitter):
        trace = make_trace(trace_id="trace_t6" + "0" * 26)
        processor.on_trace_start(trace)
        span = make_span(
            agent_span_data(),
            trace_id=trace.trace_id,
            span_id="span_with_parent00000000a",
            parent_id=None,
        )
        processor.on_span_start(span)
        processor.on_span_end(span)

        start, end = fake_emitter.events
        assert start.depth == end.depth


# ---------------------------------------------------------------------------
# Defensive behaviour
# ---------------------------------------------------------------------------


class TestExceptionsAreSwallowed:
    def test_emitter_raising_does_not_propagate(self, config):
        class BadEmitter:
            def emit(self, *_): raise RuntimeError("boom")
            def create_run(self, *_): raise RuntimeError("boom")
            def update_run(self, *_, **__): raise RuntimeError("boom")
            def flush(self): raise RuntimeError("boom")
            def shutdown(self): raise RuntimeError("boom")

        proc = ReverieTracingProcessor(emitter=BadEmitter(), config=config)
        trace = make_trace(trace_id="trace_t7" + "0" * 26)
        # None of these may raise.
        proc.on_trace_start(trace)
        span = make_span(agent_span_data(), trace_id=trace.trace_id)
        proc.on_span_start(span)
        proc.on_span_end(span)
        proc.on_trace_end(trace)
        proc.force_flush()
        proc.shutdown()
