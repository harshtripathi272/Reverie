"""HTTP-level tests for the Phase 1 replay endpoints."""

from __future__ import annotations

from .conftest import (
    goal_event,
    make_event,
    make_run_create,
    make_uuid,
    retry_event,
    tool_returned_event,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_run(client, *, with_failure: bool = False) -> str:
    body = make_run_create()
    r = await client.post("/api/v1/runs", json=body)
    assert r.status_code == 201
    rid = body["runId"]

    events = [
        goal_event(rid, timestamp=1_700_000_000_000),
        make_event(rid, timestamp=1_700_000_000_001),  # tool.called
        tool_returned_event(rid, timestamp=1_700_000_000_002, token_cost=10),
        make_event(rid, timestamp=1_700_000_000_003),
        tool_returned_event(rid, timestamp=1_700_000_000_004, token_cost=15),
    ]
    if with_failure:
        events.append(
            retry_event(
                rid,
                event_type="retry.exhausted",
                timestamp=1_700_000_000_005,
            )
        )
    r = await client.post("/api/v1/events/batch", json=events)
    assert r.status_code == 201, r.text
    return rid


# ---------------------------------------------------------------------------
# /snapshot
# ---------------------------------------------------------------------------


class TestSnapshotEndpoint:
    async def test_returns_terminal_state_when_at_omitted(self, client):
        rid = await _seed_run(client)
        r = await client.get(f"/api/v1/runs/{rid}/snapshot")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["runId"] == rid
        assert body["eventCount"] == 5
        assert body["totalToolCalls"] == 2

    async def test_returns_state_at_specific_index(self, client):
        rid = await _seed_run(client)
        r = await client.get(f"/api/v1/runs/{rid}/snapshot?at=2")
        assert r.status_code == 200
        body = r.json()
        assert body["eventCount"] == 2
        # After [goal.created, tool.called]: one active goal, one active tool.
        assert len(body["activeGoals"]) == 1
        assert len(body["activeTools"]) == 1

    async def test_at_zero_returns_empty_state(self, client):
        rid = await _seed_run(client)
        r = await client.get(f"/api/v1/runs/{rid}/snapshot?at=0")
        assert r.status_code == 200
        body = r.json()
        assert body["eventCount"] == 0
        assert body["activeGoals"] == []

    async def test_out_of_range_returns_404(self, client):
        rid = await _seed_run(client)
        r = await client.get(f"/api/v1/runs/{rid}/snapshot?at=999")
        assert r.status_code == 404
        assert r.json()["error"] == "snapshot_out_of_range"

    async def test_unknown_run_returns_404(self, client):
        r = await client.get(f"/api/v1/runs/{make_uuid()}/snapshot")
        assert r.status_code == 404
        assert r.json()["error"] == "run_not_found"

    async def test_snapshot_uses_camelcase_wire_format(self, client):
        rid = await _seed_run(client)
        body = (await client.get(f"/api/v1/runs/{rid}/snapshot")).json()
        # Sanity: every top-level key is camelCase.
        for key in body:
            assert "_" not in key, f"unexpected snake_case key on wire: {key}"


# ---------------------------------------------------------------------------
# /timeline
# ---------------------------------------------------------------------------


class TestTimelineEndpoint:
    async def test_returns_compact_rows_in_order(self, client):
        rid = await _seed_run(client)
        r = await client.get(f"/api/v1/runs/{rid}/timeline")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 5
        # Order is by timestamp ASC.
        timestamps = [r["timestamp"] for r in rows]
        assert timestamps == sorted(timestamps)
        # Each row has only the compact fields.
        for row in rows:
            assert set(row.keys()) == {
                "id",
                "type",
                "parentId",
                "depth",
                "timestamp",
                "durationMs",
                "anomaly",
            }

    async def test_unknown_run_returns_404(self, client):
        r = await client.get(f"/api/v1/runs/{make_uuid()}/timeline")
        assert r.status_code == 404

    async def test_timeline_supports_pagination(self, client):
        rid = await _seed_run(client)
        r = await client.get(f"/api/v1/runs/{rid}/timeline?limit=2&offset=1")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 2
        # offset=1 skips the goal.created event.
        assert rows[0]["timestamp"] == 1_700_000_000_001


# ---------------------------------------------------------------------------
# /failures
# ---------------------------------------------------------------------------


class TestFailuresEndpoint:
    async def test_no_failures_returns_404(self, client):
        rid = await _seed_run(client, with_failure=False)
        r = await client.get(f"/api/v1/runs/{rid}/failures")
        assert r.status_code == 404
        assert r.json()["error"] == "no_failures"

    async def test_returns_first_failure_with_state(self, client):
        rid = await _seed_run(client, with_failure=True)
        r = await client.get(f"/api/v1/runs/{rid}/failures")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["index"] == 6  # last event is the retry.exhausted
        assert body["event"]["type"] == "retry.exhausted"
        # State BEFORE the failure should not yet count this failure.
        sb = body["stateBefore"]
        assert sb["totalFailures"] == 0
        assert sb["eventCount"] == 5

    async def test_unknown_run_returns_404(self, client):
        r = await client.get(f"/api/v1/runs/{make_uuid()}/failures")
        assert r.status_code == 404
