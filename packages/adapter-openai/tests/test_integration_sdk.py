"""Integration test for the full SDK → adapter → HTTP pipeline.

We drive the OpenAI Agents SDK's tracing surface directly (no LLM calls) so
the test is hermetic: no API key, no network beyond pytest-httpx mocks.

This is the Phase 0.3 gate condition: a trace lifecycle with a few spans
must result in (1) one ``POST /api/v1/runs``, (2) one or more ``POST
/api/v1/events/batch`` calls containing schema-valid CognitiveEvents in the
right order, and (3) one ``PATCH /api/v1/runs/{id}``.
"""

from __future__ import annotations

import json
import time

import pytest
from agents.tracing import (
    add_trace_processor,
    agent_span,
    function_span,
    set_trace_processors,
    trace,
)
from pytest_httpx import HTTPXMock
from reverie_schema import CognitiveEvent

from reverie_openai.config import AdapterConfig
from reverie_openai.emitter import Emitter
from reverie_openai.processor import ReverieTracingProcessor

BASE_URL = "http://test-backend:9999"


@pytest.fixture
def non_mocked_hosts() -> list[str]:
    return []


@pytest.fixture
def adapter(httpx_mock: HTTPXMock):
    """Wire up a real Emitter + Processor and register them with the SDK."""

    # Mock all three endpoints generously — pytest-httpx matches by URL only.
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/api/v1/runs",
        json={"ok": True},
        is_reusable=True,
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/api/v1/events/batch",
        json={"ok": True, "count": 0},
        is_reusable=True,
    )
    # PATCH .../runs/<id> — match by regex prefix using ``url=`` callable trick.
    # pytest-httpx matches exact URL, so we register many possible run IDs by
    # using a wildcard-ish approach: register one per call site.
    # Easier: set a catch-all PATCH responder via match_content / match_url.
    import re

    httpx_mock.add_response(
        method="PATCH",
        url=re.compile(rf"^{re.escape(BASE_URL)}/api/v1/runs/.*$"),
        json={"ok": True},
        is_reusable=True,
    )

    cfg = AdapterConfig(
        backend_url=BASE_URL,
        agent_id="test-agent",
        queue_size=1000,
        batch_size=50,
        flush_interval_ms=20,
        request_timeout_seconds=2.0,
    )
    emitter = Emitter(cfg)
    emitter.start()
    processor = ReverieTracingProcessor(emitter, cfg)
    # Replace any previously-registered processors so other tests don't
    # interfere. The SDK's default-batch-export processor is also disabled.
    set_trace_processors([processor])

    try:
        yield emitter, processor, httpx_mock
    finally:
        processor.shutdown()
        # Clean SDK state for the next test.
        set_trace_processors([])


def _wait_for(predicate, timeout: float = 3.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _collect_event_bodies(httpx_mock: HTTPXMock) -> list[list[dict]]:
    """Return a list of batches; each batch is a list of event dicts."""

    out: list[list[dict]] = []
    for req in httpx_mock.get_requests():
        if req.method == "POST" and req.url.path == "/api/v1/events/batch":
            out.append(json.loads(req.read()))
    return out


# ---------------------------------------------------------------------------
# The gate: a real trace produces real, valid events
# ---------------------------------------------------------------------------


def test_trace_with_spans_produces_validated_events(adapter):
    emitter, _processor, httpx_mock = adapter

    # Drive the SDK exactly the way Runner.run does internally.
    with trace("research-workflow", group_id="session-1") as t:
        with agent_span(name="planner") as _planner:
            with function_span(name="search_web", input='{"query":"x"}') as fn:
                fn.span_data.output = "results"
            with function_span(name="write_summary", input='{"title":"y"}') as fn2:
                fn2.span_data.output = "ok"
        # Trace exits → on_trace_end fires.

    trace_id = t.trace_id

    # Wait until everything has been posted.
    assert _wait_for(lambda: emitter.posted_count >= 6), (
        f"emitter never posted 6 events: posted={emitter.posted_count}, "
        f"failed={emitter.failed_count}, dropped={emitter.dropped_count}"
    )

    # 1) Run create
    run_creates = [
        r for r in httpx_mock.get_requests()
        if r.method == "POST" and r.url.path == "/api/v1/runs"
    ]
    assert len(run_creates) == 1
    body = json.loads(run_creates[0].read())
    assert body["sessionId"] == "session-1"
    assert body["agentId"] == "test-agent"
    assert body["runtime"] == "openai-agents"
    assert body["goal"] == "research-workflow"

    # 2) Events: one or more batches, six total (3 spans × start+end).
    batches = _collect_event_bodies(httpx_mock)
    flat = [e for batch in batches for e in batch]
    assert len(flat) == 6, f"expected 6 events, got {len(flat)}: {[e['type'] for e in flat]}"

    types = [e["type"] for e in flat]
    assert types.count("goal.created") == 1
    assert types.count("goal.completed") == 1
    assert types.count("tool.called") == 2
    assert types.count("tool.returned") == 2

    # Every event must validate against the schema.
    for raw in flat:
        CognitiveEvent.model_validate(raw)

    # All belong to the same run.
    run_ids = {e["runId"] for e in flat}
    assert len(run_ids) == 1

    # 3) Run completion
    completes = [
        r for r in httpx_mock.get_requests()
        if r.method == "PATCH" and r.url.path.startswith("/api/v1/runs/")
    ]
    assert len(completes) == 1
    patch_body = json.loads(completes[0].read())
    assert patch_body["status"] == "completed"


def test_event_topology_is_a_tree(adapter):
    emitter, _processor, httpx_mock = adapter

    with trace("topology-check"):
        with agent_span(name="planner"):
            with function_span(name="search", input="{}") as f:
                f.span_data.output = "ok"

    assert _wait_for(lambda: emitter.posted_count >= 4)

    flat = [e for batch in _collect_event_bodies(httpx_mock) for e in batch]

    # Build id → event lookup.
    by_id = {e["id"]: e for e in flat}

    # Every parentId must either be None or point at another emitted event.
    for evt in flat:
        pid = evt["parentId"]
        if pid is not None:
            assert pid in by_id, f"orphan parentId={pid} on event id={evt['id']}"

    # Depth is monotonically nondecreasing along any parent chain.
    for evt in flat:
        depth = evt["depth"]
        cur_pid = evt["parentId"]
        while cur_pid is not None:
            parent = by_id.get(cur_pid)
            if parent is None:
                break
            assert depth >= parent["depth"]
            cur_pid = parent["parentId"]


def test_function_span_with_error_emits_tool_failed(adapter):
    emitter, _processor, httpx_mock = adapter

    with trace("error-path"):
        with agent_span(name="planner"):
            with function_span(name="bad_tool", input="{}") as fn:
                fn.set_error({"message": "kaboom", "data": None})

    assert _wait_for(lambda: emitter.posted_count >= 4)

    flat = [e for batch in _collect_event_bodies(httpx_mock) for e in batch]
    types = [e["type"] for e in flat]
    assert "tool.failed" in types
    failed = next(e for e in flat if e["type"] == "tool.failed")
    assert failed["payload"]["success"] is False
    assert "kaboom" in failed["payload"]["errorMessage"]
