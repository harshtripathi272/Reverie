"""Tests for the DB-cached SummaryService (substep 3.3)."""

from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from reverie_api.ai.client import DEFAULT_API_URL, ClaudeClient
from reverie_api.ai.summary import SummaryService


@pytest.fixture
def non_mocked_hosts() -> list[str]:
    return []


@pytest.fixture
def configured_service(app):
    """Service backed by a configured Claude client (api key set)."""

    client = ClaudeClient(api_key="sk-test")
    return SummaryService(app.state.db, client)


@pytest.fixture
def unconfigured_service(app):
    """Service backed by a Claude client with no key."""

    client = ClaudeClient(api_key="")
    return SummaryService(app.state.db, client)


_SAMPLE_EVENTS = [
    {
        "type": "goal.created",
        "depth": 0,
        "durationMs": None,
        "payload": {"_type": "goal", "intent": "research observability"},
    },
    {
        "type": "tool.failed",
        "depth": 1,
        "durationMs": 12.0,
        "payload": {
            "_type": "tool",
            "toolName": "search",
            "success": False,
            "errorMessage": "timeout",
        },
    },
]


# ---------------------------------------------------------------------------
# Cluster summarization
# ---------------------------------------------------------------------------


class TestSummarizeCluster:
    async def test_no_api_key_returns_no_api_key_status_no_call(
        self, unconfigured_service, httpx_mock: HTTPXMock
    ):
        result = await unconfigured_service.summarize_cluster(
            cluster_id="goal-abc",
            events=_SAMPLE_EVENTS,
        )
        assert result.status == "no_api_key"
        # No call to the API.
        assert len(httpx_mock.get_requests()) == 0

    async def test_calls_api_once_then_caches(
        self, configured_service, httpx_mock: HTTPXMock
    ):
        httpx_mock.add_response(
            method="POST",
            url=DEFAULT_API_URL,
            json={
                "content": [
                    {"type": "text", "text": "agent looped on a flaky search."}
                ],
            },
        )
        # First call → API request.
        r1 = await configured_service.summarize_cluster(
            cluster_id="goal-1", events=_SAMPLE_EVENTS
        )
        assert r1.is_ok
        assert "looped" in r1.text
        # Second call (same content) → cache hit, no extra request.
        r2 = await configured_service.summarize_cluster(
            cluster_id="goal-1", events=_SAMPLE_EVENTS
        )
        assert r2.is_ok
        assert r2.text == r1.text
        assert len(httpx_mock.get_requests()) == 1

    async def test_force_refresh_bypasses_cache(
        self, configured_service, httpx_mock: HTTPXMock
    ):
        httpx_mock.add_response(
            method="POST",
            url=DEFAULT_API_URL,
            json={"content": [{"type": "text", "text": "first"}]},
            is_reusable=True,
        )
        await configured_service.summarize_cluster(
            cluster_id="goal-2", events=_SAMPLE_EVENTS
        )
        await configured_service.summarize_cluster(
            cluster_id="goal-2", events=_SAMPLE_EVENTS, force_refresh=True
        )
        # Two API calls.
        assert len(httpx_mock.get_requests()) == 2

    async def test_different_content_different_cache_row(
        self, configured_service, httpx_mock: HTTPXMock
    ):
        httpx_mock.add_response(
            method="POST",
            url=DEFAULT_API_URL,
            json={"content": [{"type": "text", "text": "alpha"}]},
            is_reusable=True,
        )
        await configured_service.summarize_cluster(
            cluster_id="goal-x", events=_SAMPLE_EVENTS
        )
        # Different events → different content_hash → fresh API call.
        await configured_service.summarize_cluster(
            cluster_id="goal-x",
            events=[*_SAMPLE_EVENTS, {"type": "goal.failed", "depth": 0, "durationMs": None, "payload": {"_type": "goal"}}],
        )
        assert len(httpx_mock.get_requests()) == 2

    async def test_failure_status_is_persisted_in_cache(
        self, configured_service, httpx_mock: HTTPXMock
    ):
        httpx_mock.add_response(
            method="POST",
            url=DEFAULT_API_URL,
            status_code=500,
            json={"error": "boom"},
        )
        # First call returns api_error.
        r = await configured_service.summarize_cluster(
            cluster_id="goal-y", events=_SAMPLE_EVENTS
        )
        assert r.status == "api_error"
        # Second call returns the same cached failure — no new API call.
        r2 = await configured_service.summarize_cluster(
            cluster_id="goal-y", events=_SAMPLE_EVENTS
        )
        assert r2.status == "api_error"
        assert r2.detail == "from cache"
        assert len(httpx_mock.get_requests()) == 1


# ---------------------------------------------------------------------------
# Comparison summarization
# ---------------------------------------------------------------------------


class TestSummarizeComparison:
    async def test_comparison_returns_ai_text(
        self, configured_service, httpx_mock: HTTPXMock
    ):
        httpx_mock.add_response(
            method="POST",
            url=DEFAULT_API_URL,
            json={
                "content": [
                    {
                        "type": "text",
                        "text": "Run B failed because the search tool timed out at step 4.",
                    }
                ],
            },
        )
        diff = {
            "divergencePoint": {"runA": "evt-7", "runB": "evt-7"},
            "tokenDelta": 1200,
            "extraToolCallsInB": ["search_web"],
        }
        r = await configured_service.summarize_comparison(
            comparison_id="run1:run2", diff=diff
        )
        assert r.is_ok
        assert "Run B failed" in r.text
