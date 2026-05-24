"""Tests for the annotations + guidance API.

Covers:
- Single + batch creation
- Listing per-run
- Per-annotation + bulk delete
- Per-agent guidance rendering (prompt prefix + Markdown)
- Tag filtering
- Default scope behaviour (only ``agent``-scoped annotations carry forward)
- 404s on missing runs / annotations
"""

from __future__ import annotations

import pytest

from .conftest import goal_event, make_run_create, make_uuid, tool_returned_event


@pytest.mark.asyncio
async def test_create_single_annotation_returns_full_record(client):
    run = (
        await client.post("/api/v1/runs", json=make_run_create(agentId="alice"))
    ).json()
    evt_id = make_uuid()
    event = goal_event(run["id"], id=evt_id)
    await client.post("/api/v1/events", json=event)

    resp = await client.post(
        f"/api/v1/runs/{run['id']}/annotations",
        json={
            "nodeId": evt_id,
            "kind": "avoid",
            "note": "this approach was a dead end",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "avoid"
    assert body["nodeId"] == evt_id
    assert body["note"] == "this approach was a dead end"
    assert body["agentId"] == "alice"
    assert body["scope"] == "agent"
    assert body["runId"] == run["id"]
    assert "id" in body and "createdAt" in body


@pytest.mark.asyncio
async def test_create_batch_returns_list_envelope(client):
    run = (
        await client.post("/api/v1/runs", json=make_run_create(agentId="bob"))
    ).json()

    resp = await client.post(
        f"/api/v1/runs/{run['id']}/annotations",
        json={
            "items": [
                {"nodeId": "n1", "kind": "avoid"},
                {"nodeId": "n2", "kind": "focus", "note": "explore this"},
                {"nodeId": "n3", "kind": "done"},
            ]
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "items" in body
    assert len(body["items"]) == 3
    assert {a["kind"] for a in body["items"]} == {"avoid", "focus", "done"}


@pytest.mark.asyncio
async def test_list_annotations_orders_by_created_at(client):
    run = (await client.post("/api/v1/runs", json=make_run_create())).json()

    for i, kind in enumerate(("avoid", "focus", "done", "note")):
        resp = await client.post(
            f"/api/v1/runs/{run['id']}/annotations",
            json={"nodeId": f"n-{i}", "kind": kind},
        )
        assert resp.status_code == 201

    listing = (await client.get(f"/api/v1/runs/{run['id']}/annotations")).json()
    kinds = [a["kind"] for a in listing["items"]]
    assert kinds == ["avoid", "focus", "done", "note"]


@pytest.mark.asyncio
async def test_create_against_unknown_run_404s(client):
    resp = await client.post(
        "/api/v1/runs/00000000-0000-0000-0000-000000000000/annotations",
        json={"nodeId": "n1", "kind": "avoid"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_one_annotation(client):
    run = (await client.post("/api/v1/runs", json=make_run_create())).json()
    created = (
        await client.post(
            f"/api/v1/runs/{run['id']}/annotations",
            json={"nodeId": "n1", "kind": "avoid"},
        )
    ).json()

    resp = await client.delete(f"/api/v1/annotations/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1

    listing = (await client.get(f"/api/v1/runs/{run['id']}/annotations")).json()
    assert listing["items"] == []


@pytest.mark.asyncio
async def test_delete_unknown_annotation_404s(client):
    resp = await client.delete(
        "/api/v1/annotations/00000000-0000-0000-0000-000000000000"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_bulk_delete_for_run(client):
    run = (await client.post("/api/v1/runs", json=make_run_create())).json()
    for i in range(5):
        await client.post(
            f"/api/v1/runs/{run['id']}/annotations",
            json={"nodeId": f"n-{i}", "kind": "avoid"},
        )

    resp = await client.delete(f"/api/v1/runs/{run['id']}/annotations")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 5

    listing = (await client.get(f"/api/v1/runs/{run['id']}/annotations")).json()
    assert listing["items"] == []


# ---------------------------------------------------------------------------
# Guidance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guidance_for_unannotated_agent_is_empty(client):
    resp = await client.get("/api/v1/agents/unknown-agent/guidance")
    assert resp.status_code == 200
    body = resp.json()
    assert body["agentId"] == "unknown-agent"
    assert body["items"] == []
    assert body["promptPrefix"] == ""


@pytest.mark.asyncio
async def test_guidance_aggregates_across_runs_for_same_agent(client):
    # Two runs of the same agent.
    run_a = (
        await client.post(
            "/api/v1/runs",
            json=make_run_create(agentId="research-bot"),
        )
    ).json()
    run_b = (
        await client.post(
            "/api/v1/runs",
            json=make_run_create(agentId="research-bot"),
        )
    ).json()

    # Insert events so the event-type lookup populates the rendered prefix.
    evt_a = make_uuid()
    evt_b = make_uuid()
    await client.post("/api/v1/events", json=goal_event(run_a["id"], id=evt_a))
    await client.post(
        "/api/v1/events",
        json=tool_returned_event(run_b["id"], id=evt_b),
    )

    # Annotate one node in each run.
    await client.post(
        f"/api/v1/runs/{run_a['id']}/annotations",
        json={"nodeId": evt_a, "kind": "avoid", "note": "spawned too many subagents"},
    )
    await client.post(
        f"/api/v1/runs/{run_b['id']}/annotations",
        json={"nodeId": evt_b, "kind": "focus", "note": "this lookup was efficient"},
    )

    body = (await client.get("/api/v1/agents/research-bot/guidance")).json()
    assert body["agentId"] == "research-bot"
    assert len(body["items"]) == 2

    prefix = body["promptPrefix"]
    assert "PRIOR RUN GUIDANCE FROM USER" in prefix
    assert "Avoid these approaches" in prefix
    assert "Focus on these directions" in prefix
    assert "spawned too many subagents" in prefix
    assert "this lookup was efficient" in prefix
    # The event-type label should be inlined.
    assert "goal.created" in prefix
    assert "tool.returned" in prefix


@pytest.mark.asyncio
async def test_guidance_default_excludes_run_scoped_annotations(client):
    run = (
        await client.post(
            "/api/v1/runs", json=make_run_create(agentId="scope-bot")
        )
    ).json()
    evt_1 = make_uuid()
    evt_2 = make_uuid()
    await client.post("/api/v1/events", json=goal_event(run["id"], id=evt_1))
    await client.post("/api/v1/events", json=goal_event(run["id"], id=evt_2))

    await client.post(
        f"/api/v1/runs/{run['id']}/annotations",
        json={"nodeId": evt_1, "kind": "avoid", "scope": "agent"},
    )
    await client.post(
        f"/api/v1/runs/{run['id']}/annotations",
        json={"nodeId": evt_2, "kind": "avoid", "scope": "run"},
    )

    body = (await client.get("/api/v1/agents/scope-bot/guidance")).json()
    # Default scope filter is "agent" — the run-scoped annotation must not appear.
    assert len(body["items"]) == 1
    assert body["items"][0]["nodeId"] == evt_1


@pytest.mark.asyncio
async def test_guidance_excludes_notes_from_prompt_prefix_by_default(client):
    run = (
        await client.post(
            "/api/v1/runs", json=make_run_create(agentId="note-bot")
        )
    ).json()
    evt_id = make_uuid()
    await client.post("/api/v1/events", json=goal_event(run["id"], id=evt_id))

    await client.post(
        f"/api/v1/runs/{run['id']}/annotations",
        json={"nodeId": evt_id, "kind": "note", "note": "interesting branch"},
    )

    body = (await client.get("/api/v1/agents/note-bot/guidance")).json()
    # `note` is not in the default kinds list — items should be empty.
    assert body["items"] == []
    assert body["promptPrefix"] == ""

    # Explicitly request notes too.
    body2 = (
        await client.get(
            "/api/v1/agents/note-bot/guidance",
            params={"kinds": "avoid,focus,done,note"},
        )
    ).json()
    assert len(body2["items"]) == 1
    assert body2["items"][0]["kind"] == "note"


@pytest.mark.asyncio
async def test_guidance_tag_filter(client):
    run = (
        await client.post("/api/v1/runs", json=make_run_create(agentId="tag-bot"))
    ).json()
    evts = [make_uuid() for _ in range(3)]
    for e in evts:
        await client.post(
            "/api/v1/events", json=goal_event(run["id"], id=e)
        )

    await client.post(
        f"/api/v1/runs/{run['id']}/annotations",
        json={"nodeId": evts[0], "kind": "avoid", "tag": "research"},
    )
    await client.post(
        f"/api/v1/runs/{run['id']}/annotations",
        json={"nodeId": evts[1], "kind": "avoid", "tag": "coding"},
    )
    await client.post(
        f"/api/v1/runs/{run['id']}/annotations",
        json={"nodeId": evts[2], "kind": "avoid"},  # untagged → matches all
    )

    body = (
        await client.get(
            "/api/v1/agents/tag-bot/guidance", params={"tag": "research"}
        )
    ).json()
    node_ids = {item["nodeId"] for item in body["items"]}
    assert node_ids == {evts[0], evts[2]}


@pytest.mark.asyncio
async def test_guidance_clear_wipes_agent_annotations(client):
    run = (
        await client.post(
            "/api/v1/runs", json=make_run_create(agentId="wipe-bot")
        )
    ).json()
    for i in range(4):
        await client.post(
            f"/api/v1/runs/{run['id']}/annotations",
            json={"nodeId": f"n-{i}", "kind": "avoid"},
        )

    resp = await client.delete("/api/v1/agents/wipe-bot/guidance")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 4

    body = (await client.get("/api/v1/agents/wipe-bot/guidance")).json()
    assert body["items"] == []


@pytest.mark.asyncio
async def test_guidance_does_not_cross_agents(client):
    run_a = (
        await client.post("/api/v1/runs", json=make_run_create(agentId="a-bot"))
    ).json()
    run_b = (
        await client.post("/api/v1/runs", json=make_run_create(agentId="b-bot"))
    ).json()

    evt_a = make_uuid()
    evt_b = make_uuid()
    await client.post("/api/v1/events", json=goal_event(run_a["id"], id=evt_a))
    await client.post("/api/v1/events", json=goal_event(run_b["id"], id=evt_b))

    await client.post(
        f"/api/v1/runs/{run_a['id']}/annotations",
        json={"nodeId": evt_a, "kind": "avoid"},
    )
    await client.post(
        f"/api/v1/runs/{run_b['id']}/annotations",
        json={"nodeId": evt_b, "kind": "avoid"},
    )

    a_body = (await client.get("/api/v1/agents/a-bot/guidance")).json()
    b_body = (await client.get("/api/v1/agents/b-bot/guidance")).json()
    assert len(a_body["items"]) == 1
    assert len(b_body["items"]) == 1
    assert a_body["items"][0]["nodeId"] == evt_a
    assert b_body["items"][0]["nodeId"] == evt_b


@pytest.mark.asyncio
async def test_invalid_kinds_query_param_400s(client):
    resp = await client.get(
        "/api/v1/agents/some-bot/guidance", params={"kinds": "avoid,bogus"}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_invalid_kind_in_body_422s(client):
    run = (await client.post("/api/v1/runs", json=make_run_create())).json()
    resp = await client.post(
        f"/api/v1/runs/{run['id']}/annotations",
        json={"nodeId": "n1", "kind": "lol-not-valid"},
    )
    assert resp.status_code == 422
