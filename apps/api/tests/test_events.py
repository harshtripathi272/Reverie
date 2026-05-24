"""Event ingestion endpoint tests.

Covers:
  - single insert
  - batch insert (atomic)
  - aggregate counter updates
  - rejection of events for unknown runs
  - rejection of malformed events (Pydantic validation)
  - duplicate event id handling
  - listing events back in timestamp order
"""

from __future__ import annotations

from .conftest import (
    goal_event,
    make_event,
    make_run_create,
    make_uuid,
    retry_event,
    subagent_event,
    tool_returned_event,
)


async def _create_run(client) -> dict:
    body = make_run_create()
    resp = await client.post("/api/v1/runs", json=body)
    assert resp.status_code == 201
    return body


async def test_post_single_event(client):
    run = await _create_run(client)
    evt = goal_event(run["runId"])

    resp = await client.post("/api/v1/events", json=evt)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["id"] == evt["id"]


async def test_post_event_for_unknown_run_returns_404(client):
    evt = goal_event(make_uuid())
    resp = await client.post("/api/v1/events", json=evt)
    assert resp.status_code == 404
    assert resp.json()["error"] == "batch_unknown_runs"


async def test_post_event_with_malformed_payload_returns_422(client):
    run = await _create_run(client)
    bad = goal_event(run["runId"])
    bad["payload"]["_type"] = "wat"
    resp = await client.post("/api/v1/events", json=bad)
    assert resp.status_code == 422


async def test_post_event_with_negative_depth_returns_422(client):
    run = await _create_run(client)
    bad = goal_event(run["runId"])
    bad["depth"] = -1
    resp = await client.post("/api/v1/events", json=bad)
    assert resp.status_code == 422


async def test_post_event_with_extra_field_returns_422(client):
    run = await _create_run(client)
    bad = goal_event(run["runId"])
    bad["secret"] = "no"
    resp = await client.post("/api/v1/events", json=bad)
    assert resp.status_code == 422


async def test_post_batch_atomic_and_aggregates_update(client):
    run = await _create_run(client)
    rid = run["runId"]

    batch = [
        goal_event(rid, timestamp=1_700_000_000_001),
        tool_returned_event(rid, token_cost=120, timestamp=1_700_000_000_002),
        tool_returned_event(rid, token_cost=80, timestamp=1_700_000_000_003),
        retry_event(rid, timestamp=1_700_000_000_004),
        subagent_event(rid, timestamp=1_700_000_000_005),
    ]

    resp = await client.post("/api/v1/events/batch", json=batch)
    assert resp.status_code == 201, resp.text
    assert resp.json()["count"] == 5

    # Aggregates: 5 events total, 200 tokens (from two tool.returned), 0
    # tool.called events (we sent only tool.returned), 1 retry, 1 subagent.
    fetched = (await client.get(f"/api/v1/runs/{rid}")).json()
    assert fetched["totalEvents"] == 5
    assert fetched["totalTokens"] == 200
    assert fetched["totalToolCalls"] == 0  # only counts tool.called
    assert fetched["totalRetries"] == 1
    assert fetched["totalSubagents"] == 1


async def test_tool_called_increments_tool_calls_counter(client):
    run = await _create_run(client)
    rid = run["runId"]

    batch = [make_event(rid, timestamp=1_700_000_000_010 + i) for i in range(3)]
    resp = await client.post("/api/v1/events/batch", json=batch)
    assert resp.status_code == 201

    fetched = (await client.get(f"/api/v1/runs/{rid}")).json()
    assert fetched["totalToolCalls"] == 3


async def test_post_batch_atomic_on_unknown_run(client):
    """If any event references an unknown run, the entire batch is rejected
    and nothing is persisted."""

    run = await _create_run(client)
    rid = run["runId"]
    bogus_run_id = make_uuid()

    batch = [
        goal_event(rid, timestamp=1),
        goal_event(bogus_run_id, timestamp=2),
        goal_event(rid, timestamp=3),
    ]
    resp = await client.post("/api/v1/events/batch", json=batch)
    assert resp.status_code == 404
    err = resp.json()
    assert err["error"] == "batch_unknown_runs"
    assert bogus_run_id in err["context"]["missingRunIds"]

    # Nothing should have been inserted.
    fetched = (await client.get(f"/api/v1/runs/{rid}")).json()
    assert fetched["totalEvents"] == 0


async def test_post_batch_rejects_empty(client):
    resp = await client.post("/api/v1/events/batch", json=[])
    assert resp.status_code == 400


async def test_post_batch_rejects_oversize(client):
    run = await _create_run(client)
    rid = run["runId"]
    batch = [make_event(rid, timestamp=i) for i in range(1001)]
    resp = await client.post("/api/v1/events/batch", json=batch)
    assert resp.status_code == 413


async def test_post_batch_with_one_invalid_event_returns_422(client):
    run = await _create_run(client)
    rid = run["runId"]
    batch = [
        goal_event(rid, timestamp=1),
        # malformed: bad payload._type
        {**goal_event(rid, timestamp=2), "payload": {"_type": "wat"}},
    ]
    resp = await client.post("/api/v1/events/batch", json=batch)
    assert resp.status_code == 422

    # Atomic: nothing was persisted.
    fetched = (await client.get(f"/api/v1/runs/{rid}")).json()
    assert fetched["totalEvents"] == 0


async def test_duplicate_event_id_is_rejected(client):
    run = await _create_run(client)
    rid = run["runId"]
    e1 = goal_event(rid)
    e2 = make_event(rid, id=e1["id"])  # same id, different content

    r1 = await client.post("/api/v1/events", json=e1)
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/events", json=e2)
    assert r2.status_code == 409
    assert r2.json()["error"] == "duplicate_event"
    fetched = (await client.get(f"/api/v1/runs/{rid}")).json()
    assert fetched["totalEvents"] == 1


async def test_duplicate_event_in_batch_is_atomic(client):
    """Two events with the same id within one batch must reject the whole
    batch and persist nothing."""

    run = await _create_run(client)
    rid = run["runId"]
    a = goal_event(rid, timestamp=1)
    b = make_event(rid, id=a["id"], timestamp=2)  # collides with `a`
    resp = await client.post("/api/v1/events/batch", json=[a, b])
    assert resp.status_code == 409
    assert resp.json()["error"] == "duplicate_event"

    fetched = (await client.get(f"/api/v1/runs/{rid}")).json()
    assert fetched["totalEvents"] == 0


async def test_list_events_returns_in_timestamp_order(client):
    run = await _create_run(client)
    rid = run["runId"]

    # Insert out of order.
    batch = [
        make_event(rid, timestamp=300),
        make_event(rid, timestamp=100),
        make_event(rid, timestamp=200),
    ]
    resp = await client.post("/api/v1/events/batch", json=batch)
    assert resp.status_code == 201

    resp = await client.get(f"/api/v1/runs/{rid}/events")
    assert resp.status_code == 200
    events = resp.json()
    assert [e["timestamp"] for e in events] == [100, 200, 300]


async def test_list_events_for_unknown_run_returns_404(client):
    resp = await client.get(f"/api/v1/runs/{make_uuid()}/events")
    assert resp.status_code == 404


async def test_list_events_paginates(client):
    run = await _create_run(client)
    rid = run["runId"]
    batch = [make_event(rid, timestamp=1_700_000_000_000 + i) for i in range(10)]
    await client.post("/api/v1/events/batch", json=batch)

    resp = await client.get(f"/api/v1/runs/{rid}/events?limit=4&offset=2")
    assert resp.status_code == 200
    page = resp.json()
    assert len(page) == 4
    # offset=2 with timestamp ordering means we skip events 0 and 1.
    assert page[0]["timestamp"] == 1_700_000_000_002
    assert page[-1]["timestamp"] == 1_700_000_000_005


async def test_event_payload_round_trip(client):
    """Inserted event JSON must match what /events returns, modulo formatting."""

    run = await _create_run(client)
    rid = run["runId"]
    evt = tool_returned_event(rid, token_cost=42, timestamp=1_700_000_001_234)
    evt["durationMs"] = 99.5
    evt["salience"] = 0.6
    evt["anomaly"] = True

    resp = await client.post("/api/v1/events", json=evt)
    assert resp.status_code == 201

    fetched = (await client.get(f"/api/v1/runs/{rid}/events")).json()
    assert len(fetched) == 1
    out = fetched[0]
    assert out["id"] == evt["id"]
    assert out["timestamp"] == evt["timestamp"]
    assert out["durationMs"] == evt["durationMs"]
    assert out["salience"] == evt["salience"]
    assert out["anomaly"] is True
    assert out["payload"]["_type"] == "tool"
    assert out["payload"]["tokenCost"] == 42
    assert out["payload"]["result"] == {"hits": 3}


async def test_parent_id_chain_round_trip(client):
    """A causally-linked tree of events stores and returns its topology."""

    run = await _create_run(client)
    rid = run["runId"]

    root = goal_event(rid, timestamp=1)
    child = make_event(rid, timestamp=2, parentId=root["id"], depth=1)
    grand = make_event(rid, timestamp=3, parentId=child["id"], depth=2)

    resp = await client.post("/api/v1/events/batch", json=[root, child, grand])
    assert resp.status_code == 201

    events = (await client.get(f"/api/v1/runs/{rid}/events")).json()
    by_id = {e["id"]: e for e in events}
    assert by_id[root["id"]]["parentId"] is None
    assert by_id[root["id"]]["depth"] == 0
    assert by_id[child["id"]]["parentId"] == root["id"]
    assert by_id[child["id"]]["depth"] == 1
    assert by_id[grand["id"]]["parentId"] == child["id"]
    assert by_id[grand["id"]]["depth"] == 2


async def test_delete_run_cascades_events(client):
    run = await _create_run(client)
    rid = run["runId"]
    await client.post(
        "/api/v1/events/batch",
        json=[make_event(rid, timestamp=i) for i in range(3)],
    )
    assert (await client.get(f"/api/v1/runs/{rid}/events")).status_code == 200

    resp = await client.delete(f"/api/v1/runs/{rid}")
    assert resp.status_code == 200

    # Run is gone, listing events for it returns 404.
    resp = await client.get(f"/api/v1/runs/{rid}/events")
    assert resp.status_code == 404
