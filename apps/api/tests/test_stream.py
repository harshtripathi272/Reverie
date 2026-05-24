"""WebSocket /stream endpoint tests.

Starlette's TestClient is sync (it spins up a worker thread internally).
We use it instead of httpx because httpx's ASGITransport doesn't support
WebSockets.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from reverie_api.config import Settings
from reverie_api.main import create_app


@pytest.fixture
def sync_client(tmp_path):
    settings = Settings(
        db_path=tmp_path / "stream-test.db",
        host="127.0.0.1",
        port=0,
        env="development",
    )
    app = create_app(settings)
    # TestClient(app) handles lifespan startup/shutdown automatically.
    with TestClient(app) as client:
        yield client


def _make_run(client) -> dict:
    body = {
        "runId": str(uuid.uuid4()),
        "sessionId": str(uuid.uuid4()),
        "agentId": "agent-test",
        "runtime": "openai-agents",
        "startedAt": 1_700_000_000_000,
        "goal": "Test",
    }
    resp = client.post("/api/v1/runs", json=body)
    assert resp.status_code == 201, resp.text
    return body


def _goal_event(run_id: str, timestamp: int = 1) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "type": "goal.created",
        "runId": run_id,
        "sessionId": "session-test",
        "agentId": "agent-test",
        "parentId": None,
        "depth": 0,
        "timestamp": timestamp,
        "durationMs": None,
        "payload": {
            "_type": "goal",
            "intent": "test goal",
            "priority": "high",
            "context": "",
        },
        "salience": None,
        "anomaly": False,
        "schemaVersion": "1.0",
    }


def test_stream_rejects_unknown_run(sync_client):
    bogus_run_id = str(uuid.uuid4())
    with pytest.raises(Exception):
        # WebSocketDisconnect with code 1008 — TestClient surfaces this as
        # an exception when we try to enter the connection.
        with sync_client.websocket_connect(f"/stream?runId={bogus_run_id}"):
            pass


def test_stream_delivers_subsequent_events(sync_client):
    run = _make_run(sync_client)
    rid = run["runId"]

    with sync_client.websocket_connect(f"/stream?runId={rid}") as ws:
        # Publish one event after the subscriber is connected.
        evt = _goal_event(rid, timestamp=1_700_000_000_010)
        resp = sync_client.post("/api/v1/events", json=evt)
        assert resp.status_code == 201

        # Receive it on the stream.
        msg = ws.receive_text()
        body = json.loads(msg)
        assert body.get("id") == evt["id"]
        assert body.get("type") == "goal.created"
        assert body.get("payload", {}).get("intent") == "test goal"


def test_stream_filters_to_subscribed_run(sync_client):
    run_a = _make_run(sync_client)
    run_b = _make_run(sync_client)

    with sync_client.websocket_connect(f"/stream?runId={run_a['runId']}") as ws:
        # Publish to B first (must NOT be delivered).
        evt_b = _goal_event(run_b["runId"], timestamp=1)
        sync_client.post("/api/v1/events", json=evt_b)

        # Then publish to A.
        evt_a = _goal_event(run_a["runId"], timestamp=2)
        sync_client.post("/api/v1/events", json=evt_a)

        msg = ws.receive_text()
        body = json.loads(msg)
        assert body["id"] == evt_a["id"]
        assert body["runId"] == run_a["runId"]


def test_stream_delivers_batch_events_in_order(sync_client):
    run = _make_run(sync_client)
    rid = run["runId"]

    with sync_client.websocket_connect(f"/stream?runId={rid}") as ws:
        batch = [_goal_event(rid, timestamp=t) for t in (10, 20, 30)]
        resp = sync_client.post("/api/v1/events/batch", json=batch)
        assert resp.status_code == 201

        received = []
        for _ in range(3):
            received.append(json.loads(ws.receive_text()))

        assert [e["timestamp"] for e in received] == [10, 20, 30]
