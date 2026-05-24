"""HTTP route tests for the Phase 2 graph endpoints."""

from __future__ import annotations

from .conftest import (
    goal_event,
    make_event,
    make_run_create,
    make_uuid,
    tool_returned_event,
)


async def _seed(
    client,
    *,
    count: int = 5,
    with_failure: bool = False,
    clean: bool = False,
) -> str:
    """Standard fixture run for the graph route tests.

    Layout: 1 root goal, then ``count`` alternating tool.called / tool.returned
    events as children of the goal. Optionally append a tool.failed.

    Each tool call uses a unique name so the loop detector doesn't flag the
    fixture as anomalous. Token costs are zeroed in ``clean`` mode so the
    hotspot detector also stays quiet — useful for "no anomalies" assertions.
    """

    body = make_run_create()
    r = await client.post("/api/v1/runs", json=body)
    assert r.status_code == 201, r.text
    rid = body["runId"]

    g = goal_event(rid, depth=0, timestamp=0)
    events = [g]
    for i in range(1, 1 + count):
        unique_payload = {
            "_type": "tool",
            "toolName": f"tool_{i}",
            "args": {"i": i},
            "result": None if i % 2 else {"ok": True},
            "latencyMs": 10.0,
            "tokenCost": None if (i % 2 or clean) else 100,
            "success": True,
            "errorMessage": None,
        }
        type_ = "tool.called" if i % 2 else "tool.returned"
        events.append(
            make_event(
                rid,
                event_type=type_,
                payload=unique_payload,
                parentId=g["id"],
                depth=1,
                timestamp=i,
            )
        )
    if with_failure:
        events.append(
            make_event(
                rid,
                event_type="tool.failed",
                parentId=g["id"],
                depth=1,
                timestamp=99,
                payload={
                    "_type": "tool",
                    "toolName": "bad",
                    "args": {},
                    "result": None,
                    "latencyMs": 0.0,
                    "tokenCost": None,
                    "success": False,
                    "errorMessage": "boom",
                },
            )
        )
    r = await client.post("/api/v1/events/batch", json=events)
    assert r.status_code == 201, r.text
    return rid


# ---------------------------------------------------------------------------
# /graph
# ---------------------------------------------------------------------------


class TestGraphEndpoint:
    async def test_returns_full_bundle(self, client):
        rid = await _seed(client)
        r = await client.get(f"/api/v1/runs/{rid}/graph")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["runId"] == rid
        assert body["summary"]["totalNodes"] == 6  # 1 goal + 5 children
        assert len(body["nodes"]) == 6
        assert len(body["edges"]) == 5
        # Wire format must be camelCase.
        for node in body["nodes"]:
            for forbidden in ("parent_id", "zoom_level", "duration_ms"):
                assert forbidden not in node

    async def test_unknown_run_returns_404(self, client):
        r = await client.get(f"/api/v1/runs/{make_uuid()}/graph")
        assert r.status_code == 404
        assert r.json()["error"] == "run_not_found"

    async def test_level_1_filters_to_top_level_goals(self, client):
        rid = await _seed(client)
        r = await client.get(f"/api/v1/runs/{rid}/graph?level=1")
        assert r.status_code == 200
        body = r.json()
        # Only the root goal at L1.
        assert body["summary"]["totalNodes"] == 1
        assert body["summary"]["nodesPerZoom"]["1"] == 1
        assert body["summary"]["nodesPerZoom"]["3"] == 0
        # Edges that reference filtered-out nodes are dropped.
        assert body["summary"]["totalEdges"] == 0

    async def test_level_3_includes_tool_calls(self, client):
        rid = await _seed(client)
        r = await client.get(f"/api/v1/runs/{rid}/graph?level=3")
        assert r.status_code == 200
        body = r.json()
        assert body["summary"]["nodesPerZoom"]["3"] >= 4  # tool.* events

    async def test_invalid_level_rejected(self, client):
        rid = await _seed(client)
        # Level 5 is out of [1, 4] range.
        r = await client.get(f"/api/v1/runs/{rid}/graph?level=5")
        assert r.status_code == 422

    async def test_critical_path_in_failure_run(self, client):
        rid = await _seed(client, with_failure=True)
        body = (await client.get(f"/api/v1/runs/{rid}/graph")).json()
        path = body["criticalPath"]
        assert len(path) >= 2
        # First entry is the root goal id.
        nodes = {n["id"]: n for n in body["nodes"]}
        first = nodes[path[0]]
        assert first["type"] == "goal.created"
        assert first["depth"] == 0
        # On-critical-path flag is set on the same nodes.
        marked = {n["id"] for n in body["nodes"] if n["onCriticalPath"]}
        assert marked == set(path)


# ---------------------------------------------------------------------------
# /anomalies
# ---------------------------------------------------------------------------


class TestAnomaliesEndpoint:
    async def test_returns_empty_list_when_clean(self, client):
        rid = await _seed(client, clean=True)
        r = await client.get(f"/api/v1/runs/{rid}/anomalies")
        assert r.status_code == 200
        # No loops/hotspots in a clean fixture.
        assert r.json() == []

    async def test_loop_anomaly_surfaces(self, client):
        # Two identical tool.called events within 60s → loop on both.
        body = make_run_create()
        r = await client.post("/api/v1/runs", json=body)
        rid = body["runId"]

        repeat_payload = {
            "_type": "tool",
            "toolName": "search",
            "args": {"q": "x"},
            "result": None,
            "latencyMs": 0.0,
            "tokenCost": None,
            "success": True,
            "errorMessage": None,
        }
        a = make_event(rid, event_type="tool.called", payload=repeat_payload, timestamp=0)
        b = make_event(rid, event_type="tool.called", payload=repeat_payload, timestamp=10)
        r = await client.post("/api/v1/events/batch", json=[a, b])
        assert r.status_code == 201

        anomalies = (await client.get(f"/api/v1/runs/{rid}/anomalies")).json()
        assert len(anomalies) == 2
        for a in anomalies:
            assert a["kind"] == "loop"
            assert a["eventType"] == "tool.called"
            assert "loop" in a["detail"] or "search" in a["detail"]


# ---------------------------------------------------------------------------
# /criticalpath
# ---------------------------------------------------------------------------


class TestCriticalPathEndpoint:
    async def test_succeeded_run_returns_a_path(self, client):
        rid = await _seed(client)
        r = await client.get(f"/api/v1/runs/{rid}/criticalpath")
        assert r.status_code == 200
        body = r.json()
        assert body["runId"] == rid
        assert body["length"] >= 1
        assert isinstance(body["eventIds"], list)

    async def test_failure_run_returns_failure_chain(self, client):
        rid = await _seed(client, with_failure=True)
        body = (await client.get(f"/api/v1/runs/{rid}/criticalpath")).json()
        assert body["length"] >= 2

    async def test_unknown_run_returns_404(self, client):
        r = await client.get(f"/api/v1/runs/{make_uuid()}/criticalpath")
        assert r.status_code == 404
