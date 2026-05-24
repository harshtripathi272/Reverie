"""HTTP route tests for Phase 3."""

from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from reverie_api.ai.client import DEFAULT_API_URL

from .conftest import (
    goal_event,
    make_event,
    make_run_create,
    make_uuid,
    tool_returned_event,
)


@pytest.fixture
def non_mocked_hosts() -> list[str]:
    # We mock only the Anthropic API. The in-process FastAPI app is a
    # transport-level call, not an HTTP-over-network one — pytest-httpx
    # ignores it.
    return []


async def _seed(client) -> str:
    body = make_run_create()
    await client.post("/api/v1/runs", json=body)
    rid = body["runId"]
    g = goal_event(rid, depth=0, timestamp=0)
    events = [g]
    for i in range(1, 4):
        unique = {
            "_type": "tool",
            "toolName": f"tool_{i}",
            "args": {"i": i},
            "result": None if i % 2 else {"ok": True},
            "latencyMs": 10.0,
            "tokenCost": None,
            "success": True,
            "errorMessage": None,
        }
        type_ = "tool.called" if i % 2 else "tool.returned"
        events.append(
            make_event(rid, event_type=type_, payload=unique,
                       parentId=g["id"], depth=1, timestamp=i)
        )
    await client.post("/api/v1/events/batch", json=events)
    return rid


# ---------------------------------------------------------------------------
# /salience
# ---------------------------------------------------------------------------


class TestSalienceEndpoint:
    async def test_returns_scored_bundle(self, client):
        rid = await _seed(client)
        r = await client.get(f"/api/v1/runs/{rid}/salience")
        assert r.status_code == 200, r.text
        body = r.json()
        for n in body["nodes"]:
            assert n["salience"] is not None
            assert 0.0 <= n["salience"] <= 1.0

    async def test_unknown_run_returns_404(self, client):
        r = await client.get(f"/api/v1/runs/{make_uuid()}/salience")
        assert r.status_code == 404

    async def test_hide_noise_drops_low_score_nodes(self, client):
        rid = await _seed(client)
        full = (await client.get(f"/api/v1/runs/{rid}/salience")).json()
        filtered = (
            await client.get(f"/api/v1/runs/{rid}/salience?hide_noise=true")
        ).json()
        # Filter is monotonic.
        assert filtered["summary"]["totalNodes"] <= full["summary"]["totalNodes"]
        # All remaining nodes are at or above threshold.
        for n in filtered["nodes"]:
            assert n["salience"] >= 0.10

    async def test_level_filter_still_works(self, client):
        rid = await _seed(client)
        r = await client.get(f"/api/v1/runs/{rid}/salience?level=1")
        body = r.json()
        # Only L1 (the goal) at this filter.
        assert body["summary"]["nodesPerZoom"]["1"] == 1
        assert body["summary"]["nodesPerZoom"]["3"] == 0


# ---------------------------------------------------------------------------
# Cluster summary
# ---------------------------------------------------------------------------


class TestClusterSummaryEndpoint:
    async def test_cluster_not_found_returns_404(self, client):
        rid = await _seed(client)
        r = await client.post(
            f"/api/v1/runs/{rid}/clusters/does-not-exist/summary"
        )
        assert r.status_code == 404

    async def test_no_api_key_returns_no_api_key_status(self, client):
        rid = await _seed(client)
        # Find a cluster id from the bundle.
        bundle = (await client.get(f"/api/v1/runs/{rid}/graph")).json()
        cluster_id = bundle["clusters"][0]["id"]

        r = await client.post(
            f"/api/v1/runs/{rid}/clusters/{cluster_id}/summary"
        )
        assert r.status_code == 200
        body = r.json()
        assert body["clusterId"] == cluster_id
        # The default test backend has no ANTHROPIC_API_KEY.
        assert body["status"] == "no_api_key"
        assert body["summary"] == ""

    async def test_with_configured_client_returns_text(
        self, app, client, httpx_mock: HTTPXMock
    ):
        # Swap in a configured client + service for this test.
        from reverie_api.ai import (
            ClaudeClient,
            SummaryService,
            set_claude_client,
            set_summary_service,
        )

        configured = ClaudeClient(api_key="sk-test")
        set_claude_client(configured)
        set_summary_service(SummaryService(app.state.db, configured))

        httpx_mock.add_response(
            method="POST",
            url=DEFAULT_API_URL,
            json={"content": [{"type": "text", "text": "agent searched and found X"}]},
        )

        rid = await _seed(client)
        bundle = (await client.get(f"/api/v1/runs/{rid}/graph")).json()
        cluster_id = bundle["clusters"][0]["id"]

        r = await client.post(
            f"/api/v1/runs/{rid}/clusters/{cluster_id}/summary"
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "agent searched" in body["summary"]
