"""Emitter tests — verifies batching, fail-silent behavior, and shutdown.

We use ``pytest-httpx`` to mock the backend HTTP layer.
"""

from __future__ import annotations

import time

import httpx
import pytest
from pytest_httpx import HTTPXMock
from reverie_schema import CognitiveEvent, GoalPayload

from reverie_openai.config import AdapterConfig
from reverie_openai.emitter import Emitter

BASE_URL = "http://test-backend:9999"


def _config(**overrides) -> AdapterConfig:
    base: dict = dict(
        backend_url=BASE_URL,
        queue_size=1000,
        batch_size=5,
        flush_interval_ms=20,
        request_timeout_seconds=1.0,
    )
    base.update(overrides)
    return AdapterConfig(**base)


def _event(idx: int = 1) -> CognitiveEvent:
    return CognitiveEvent(
        id=f"00000000-0000-4000-8000-{idx:012x}",
        type="goal.created",
        run_id="11111111-1111-4111-8111-111111111111",
        session_id="11111111-1111-4111-8111-111111111111",
        agent_id="agent-test",
        parent_id=None,
        depth=0,
        timestamp=1_700_000_000_000 + idx,
        duration_ms=None,
        payload=GoalPayload(intent="x", priority="high", context=""),
        salience=None,
        anomaly=False,
    )


def _wait_for(predicate, timeout: float = 2.0) -> bool:
    """Poll a predicate until True or timeout. Avoids brittle sleeps."""

    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def non_mocked_hosts() -> list[str]:
    # Keep all requests intercepted.
    return []


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestEmitterDispatch:
    def test_emit_posts_a_batch(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/v1/events/batch",
            json={"ok": True, "count": 1},
        )

        em = Emitter(_config())
        em.start()
        try:
            em.emit(_event(1))
            assert _wait_for(lambda: em.posted_count >= 1)
        finally:
            em.shutdown()

        assert em.failed_count == 0
        assert em.dropped_count == 0
        assert len(httpx_mock.get_requests()) == 1

    def test_batches_coalesce(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/v1/events/batch",
            json={"ok": True, "count": 5},
        )

        em = Emitter(_config(batch_size=10))
        em.start()
        try:
            for i in range(5):
                em.emit(_event(i + 1))
            assert _wait_for(lambda: em.posted_count >= 5)
        finally:
            em.shutdown()

        # All five events go in a single POST (batch size 10, flush 20ms).
        reqs = httpx_mock.get_requests()
        assert len(reqs) == 1
        body = reqs[0].read()
        # Body is a JSON array of 5 events.
        import json as _json

        parsed = _json.loads(body)
        assert isinstance(parsed, list)
        assert len(parsed) == 5

    def test_create_run_posts_to_runs_endpoint(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/v1/runs",
            json={"ok": True},
        )

        em = Emitter(_config())
        em.start()
        try:
            em.create_run(
                {
                    "runId": "11111111-1111-4111-8111-111111111111",
                    "sessionId": "22222222-2222-4222-8222-222222222222",
                    "agentId": "a",
                    "runtime": "openai-agents",
                    "startedAt": 1_700_000_000_000,
                    "goal": "smoke",
                }
            )
            assert _wait_for(lambda: len(httpx_mock.get_requests()) >= 1)
        finally:
            em.shutdown()

    def test_update_run_patches(self, httpx_mock: HTTPXMock):
        run_id = "11111111-1111-4111-8111-111111111111"
        httpx_mock.add_response(
            method="PATCH",
            url=f"{BASE_URL}/api/v1/runs/{run_id}",
            json={"ok": True},
        )

        em = Emitter(_config())
        em.start()
        try:
            em.update_run(run_id, {"status": "completed"})
            assert _wait_for(lambda: len(httpx_mock.get_requests()) >= 1)
        finally:
            em.shutdown()


# ---------------------------------------------------------------------------
# Resilience
# ---------------------------------------------------------------------------


class TestEmitterResilience:
    def test_disabled_emitter_is_noop(self, httpx_mock: HTTPXMock):
        em = Emitter(_config(disabled=True))
        em.start()
        try:
            em.emit(_event(1))
            time.sleep(0.05)
        finally:
            em.shutdown()

        # Disabled emitter should NOT spawn a thread or hit the network.
        assert len(httpx_mock.get_requests()) == 0

    def test_drops_when_queue_is_full(self, httpx_mock: HTTPXMock):
        # No mock registered → any request would 500. We don't expect any.
        em = Emitter(_config(queue_size=1, disabled=True))
        # Skip starting the worker so the queue actually fills up.
        em.emit(_event(1))  # silently noops because disabled=True
        # Re-test in non-disabled mode but never start the consumer:
        em2 = Emitter(_config(queue_size=2))
        # Don't call start() — queue won't drain.
        for i in range(10):
            em2.emit(_event(i))
        assert em2.dropped_count >= 8  # 10 emitted, queue holds 2

    def test_backend_unreachable_does_not_raise(self, httpx_mock: HTTPXMock):
        httpx_mock.add_exception(
            httpx.ConnectError("connection refused"),
            url=f"{BASE_URL}/api/v1/events/batch",
        )

        em = Emitter(_config())
        em.start()
        try:
            em.emit(_event(1))
            assert _wait_for(lambda: em.failed_count >= 1)
        finally:
            em.shutdown()

        # Agent never sees this — no exception leaks out of public API.
        assert em.failed_count >= 1
        assert em.posted_count == 0

    def test_backend_5xx_is_recorded_as_failure(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/v1/events/batch",
            status_code=500,
            json={"error": "boom"},
        )

        em = Emitter(_config())
        em.start()
        try:
            em.emit(_event(1))
            assert _wait_for(lambda: em.failed_count >= 1)
        finally:
            em.shutdown()


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------


class TestEmitterShutdown:
    def test_shutdown_is_idempotent(self, httpx_mock: HTTPXMock):
        em = Emitter(_config())
        em.start()
        em.shutdown()
        em.shutdown()  # must not raise
