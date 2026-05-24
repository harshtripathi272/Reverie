"""Health endpoint smoke tests."""

from __future__ import annotations


async def test_health_returns_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert isinstance(body["dbUserVersion"], int)
    assert body["dbUserVersion"] >= 1
