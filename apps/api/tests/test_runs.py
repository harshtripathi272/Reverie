"""Run management endpoint tests."""

from __future__ import annotations

from .conftest import make_run_create, make_uuid


async def test_create_and_get_run(client):
    body = make_run_create()
    resp = await client.post("/api/v1/runs", json=body)
    assert resp.status_code == 201, resp.text

    created = resp.json()
    assert created["id"] == body["runId"]
    assert created["sessionId"] == body["sessionId"]
    assert created["status"] == "running"
    assert created["totalEvents"] == 0
    assert created["pinned"] is False
    assert created["tags"] == []

    # Re-fetch
    fetched = await client.get(f"/api/v1/runs/{body['runId']}")
    assert fetched.status_code == 200
    assert fetched.json() == created


async def test_get_unknown_run_returns_404(client):
    resp = await client.get(f"/api/v1/runs/{make_uuid()}")
    assert resp.status_code == 404
    err = resp.json()
    assert err["error"] == "run_not_found"
    assert "runId" in err["context"]


async def test_create_run_rejects_duplicate_id(client):
    body = make_run_create()
    r1 = await client.post("/api/v1/runs", json=body)
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/runs", json=body)
    assert r2.status_code == 409
    assert r2.json()["error"] == "duplicate_run"


async def test_create_run_rejects_invalid_payload(client):
    bad = make_run_create()
    del bad["runtime"]
    resp = await client.post("/api/v1/runs", json=bad)
    assert resp.status_code == 422  # FastAPI validation


async def test_list_runs_paginates(client):
    # Create five runs.
    created_ids = []
    for i in range(5):
        body = make_run_create(startedAt=1_700_000_000_000 + i)
        resp = await client.post("/api/v1/runs", json=body)
        assert resp.status_code == 201
        created_ids.append(body["runId"])

    # Default page
    resp = await client.get("/api/v1/runs")
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 5
    assert page["limit"] == 50
    assert page["offset"] == 0
    assert len(page["items"]) == 5
    # Most recent first.
    assert page["items"][0]["id"] == created_ids[-1]

    # Limit + offset
    resp = await client.get("/api/v1/runs?limit=2&offset=1")
    assert resp.status_code == 200
    p = resp.json()
    assert p["total"] == 5
    assert p["limit"] == 2
    assert p["offset"] == 1
    assert len(p["items"]) == 2


async def test_list_runs_filters_by_session(client):
    s1 = make_uuid()
    s2 = make_uuid()
    for _ in range(3):
        await client.post("/api/v1/runs", json=make_run_create(sessionId=s1))
    for _ in range(2):
        await client.post("/api/v1/runs", json=make_run_create(sessionId=s2))

    resp = await client.get(f"/api/v1/runs?sessionId={s1}")
    assert resp.status_code == 200
    assert resp.json()["total"] == 3

    resp = await client.get(f"/api/v1/runs?sessionId={s2}")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


async def test_patch_run_updates_status_and_completed_at(client):
    body = make_run_create()
    await client.post("/api/v1/runs", json=body)

    resp = await client.patch(
        f"/api/v1/runs/{body['runId']}",
        json={"status": "completed", "completedAt": 1_700_000_999_999},
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["status"] == "completed"
    assert updated["completedAt"] == 1_700_000_999_999


async def test_patch_run_rejects_invalid_status(client):
    body = make_run_create()
    await client.post("/api/v1/runs", json=body)
    resp = await client.patch(f"/api/v1/runs/{body['runId']}", json={"status": "exploded"})
    assert resp.status_code == 422


async def test_patch_unknown_run_returns_404(client):
    resp = await client.patch(
        f"/api/v1/runs/{make_uuid()}", json={"status": "completed"}
    )
    assert resp.status_code == 404


async def test_pin_and_unpin_run(client):
    body = make_run_create()
    await client.post("/api/v1/runs", json=body)

    resp = await client.patch(
        f"/api/v1/runs/{body['runId']}/pin", json={"pinned": True}
    )
    assert resp.status_code == 200
    assert resp.json()["pinned"] is True

    resp = await client.patch(
        f"/api/v1/runs/{body['runId']}/pin", json={"pinned": False}
    )
    assert resp.status_code == 200
    assert resp.json()["pinned"] is False


async def test_delete_run(client):
    body = make_run_create()
    await client.post("/api/v1/runs", json=body)

    resp = await client.delete(f"/api/v1/runs/{body['runId']}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    resp = await client.get(f"/api/v1/runs/{body['runId']}")
    assert resp.status_code == 404


async def test_delete_pinned_run_is_refused(client):
    body = make_run_create()
    await client.post("/api/v1/runs", json=body)
    await client.patch(f"/api/v1/runs/{body['runId']}/pin", json={"pinned": True})

    resp = await client.delete(f"/api/v1/runs/{body['runId']}")
    assert resp.status_code == 409
    assert resp.json()["error"] == "run_pinned"
