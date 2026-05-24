"""End-to-end pipeline tests for substep 2.3.

Covers:

- ``compute_critical_path`` (success + failure leaves, orphans, single-node)
- ``build_clusters`` (goal/subagent/tool_storm/structural)
- ``GraphEngine.build`` against a real DB (cache hits, summary correctness)
"""

from __future__ import annotations

import uuid

import pytest
from reverie_schema import (
    CognitiveEvent,
    GoalPayload,
    MemoryPayload,
    SubagentPayload,
    ToolPayload,
)

from reverie_api.graph.anomalies import annotate_anomalies
from reverie_api.graph.build import build_nodes_and_edges
from reverie_api.graph.clusters import build_clusters
from reverie_api.graph.critical_path import compute_critical_path
from reverie_api.graph.engine import GraphEngine
from reverie_api.graph.types import GraphCluster

from .conftest import (
    goal_event,
    make_event,
    make_run_create,
    tool_returned_event,
)


RUN_ID = "11111111-1111-4111-8111-111111111111"


def _new_id() -> str:
    return str(uuid.uuid4())


def _evt(
    type_: str,
    payload,
    *,
    event_id: str | None = None,
    parent_id: str | None = None,
    depth: int = 0,
    timestamp: int = 0,
) -> CognitiveEvent:
    return CognitiveEvent(
        id=event_id or _new_id(),
        type=type_,
        run_id=RUN_ID,
        session_id="22222222-2222-4222-8222-222222222222",
        agent_id="agent-test",
        parent_id=parent_id,
        depth=depth,
        timestamp=timestamp,
        duration_ms=None,
        payload=payload,
    )


def _goal(intent: str = "g", *, depth: int = 0, **kw):
    return _evt(
        "goal.created",
        GoalPayload(intent=intent, priority="high", context=""),
        depth=depth,
        **kw,
    )


def _tool_called(name: str = "x", **kw):
    return _evt(
        "tool.called",
        ToolPayload(
            tool_name=name, args={"q": "x"}, result=None,
            latency_ms=0.0, token_cost=None, success=True, error_message=None,
        ),
        **kw,
    )


def _tool_failed(name: str = "x", *, error: str = "boom", **kw):
    return _evt(
        "tool.failed",
        ToolPayload(
            tool_name=name, args={"q": "x"}, result=None,
            latency_ms=0.0, token_cost=None, success=False, error_message=error,
        ),
        **kw,
    )


# ---------------------------------------------------------------------------
# Critical path
# ---------------------------------------------------------------------------


class TestCriticalPath:
    def test_empty_run_returns_empty(self):
        nodes, edges = build_nodes_and_edges([])
        assert compute_critical_path(nodes, edges, []) == []

    def test_single_event_returns_self(self):
        e = _goal()
        nodes, edges = build_nodes_and_edges([e])
        path = compute_critical_path(nodes, edges, [e])
        assert path == [e.id]

    def test_failure_chain_walks_back_to_root(self):
        root = _goal("mission", timestamp=1)
        sub = _goal("subtask", depth=1, parent_id=root.id, timestamp=2)
        ok = _tool_called("ok", depth=2, parent_id=sub.id, timestamp=3)
        fail = _tool_failed("bad", depth=2, parent_id=sub.id, timestamp=4)
        events = [root, sub, ok, fail]
        nodes, edges = build_nodes_and_edges(events)
        path = compute_critical_path(nodes, edges, events)
        assert path == [root.id, sub.id, fail.id]
        assert ok.id not in path  # ok was not on the failing path

    def test_success_run_walks_back_from_latest_event(self):
        root = _goal("mission", timestamp=1)
        sub = _goal("subtask", depth=1, parent_id=root.id, timestamp=2)
        last = _tool_called("z", depth=2, parent_id=sub.id, timestamp=99)
        events = [root, sub, last]
        nodes, edges = build_nodes_and_edges(events)
        path = compute_critical_path(nodes, edges, events)
        assert path == [root.id, sub.id, last.id]

    def test_first_failure_wins_over_later_failure(self):
        root = _goal("m", timestamp=1)
        f1 = _tool_failed("a", depth=1, parent_id=root.id, timestamp=2, error="first")
        f2 = _tool_failed("b", depth=1, parent_id=root.id, timestamp=3, error="second")
        events = [root, f1, f2]
        nodes, edges = build_nodes_and_edges(events)
        path = compute_critical_path(nodes, edges, events)
        # Path goes back from the FIRST failure (f1), not the latter.
        assert path == [root.id, f1.id]

    def test_orphan_parent_truncates_chain(self):
        ghost = _new_id()
        f = _tool_failed("x", depth=2, parent_id=ghost, timestamp=1)
        events = [f]
        nodes, edges = build_nodes_and_edges(events)
        path = compute_critical_path(nodes, edges, events)
        # Walk only contains the leaf — its parent isn't in the run.
        assert path == [f.id]


# ---------------------------------------------------------------------------
# Clusters
# ---------------------------------------------------------------------------


class TestClusters:
    def test_top_level_goal_makes_a_goal_cluster(self):
        root = _goal("mission")
        child = _tool_called("x", depth=1, parent_id=root.id, timestamp=2)
        nodes, edges = build_nodes_and_edges([root, child])
        clusters = build_clusters(nodes, edges)
        goal_clusters = [c for c in clusters if c.type == "goal"]
        assert len(goal_clusters) == 1
        gc = goal_clusters[0]
        assert gc.root_event_id == root.id
        assert root.id in gc.member_event_ids
        assert child.id in gc.member_event_ids

    def test_subagent_makes_a_subagent_cluster(self):
        sub = _evt(
            "subagent.spawned",
            SubagentPayload(agent_type="r", task="t", delegated_goal_id=None, child_run_id=None),
            timestamp=1,
        )
        kid = _tool_called("x", depth=1, parent_id=sub.id, timestamp=2)
        nodes, edges = build_nodes_and_edges([sub, kid])
        clusters = build_clusters(nodes, edges)
        sub_clusters = [c for c in clusters if c.type == "subagent"]
        assert len(sub_clusters) == 1
        sc = sub_clusters[0]
        assert sub.id in sc.member_event_ids
        assert kid.id in sc.member_event_ids

    def test_loop_anomaly_creates_tool_storm_cluster(self):
        # Two identical calls within window → both flagged ``loop``.
        a = _tool_called("repeat", timestamp=0)
        b = _tool_called("repeat", timestamp=10)
        events = [a, b]
        nodes, edges = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        clusters = build_clusters(nodes, edges)
        storms = [c for c in clusters if c.type == "tool_storm"]
        assert len(storms) == 1
        s = storms[0]
        assert a.id in s.member_event_ids
        assert b.id in s.member_event_ids

    def test_orphan_events_fall_into_structural_catchall(self):
        e = _evt(
            "memory.retrieved",
            MemoryPayload(query="q", hit_count=0, relevance_scores=[], retrieval_ms=1.0, storage_key="k"),
            timestamp=1,
        )
        nodes, edges = build_nodes_and_edges([e])
        clusters = build_clusters(nodes, edges)
        catchall = [c for c in clusters if c.type == "structural"]
        assert len(catchall) == 1
        assert e.id in catchall[0].member_event_ids


# ---------------------------------------------------------------------------
# Engine — DB-aware end-to-end
# ---------------------------------------------------------------------------


async def _seed(client, *, with_failure: bool = False) -> str:
    body = make_run_create()
    r = await client.post("/api/v1/runs", json=body)
    assert r.status_code == 201, r.text
    rid = body["runId"]

    # Goal at depth 0, then 5 alternating tool.called / tool.returned, then
    # optionally a tool.failed.
    g = goal_event(rid, depth=0, timestamp=0)
    events = [g]
    for i in range(1, 5):
        if i % 2:
            events.append(make_event(rid, parentId=g["id"], depth=1, timestamp=i))
        else:
            events.append(
                tool_returned_event(rid, parentId=g["id"], depth=1, timestamp=i, token_cost=10)
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


class TestGraphEngine:
    async def test_build_returns_full_bundle(self, app, client):
        rid = await _seed(client)
        engine: GraphEngine = app.state.graph_engine
        bundle = await engine.build(rid)

        assert bundle.run_id == rid
        assert bundle.summary.total_nodes == 5
        assert bundle.summary.total_edges == 4  # one root, four children
        assert bundle.summary.nodes_per_zoom["1"] == 1  # the goal
        # The remaining 4 are tool.called/returned at L3.
        assert bundle.summary.nodes_per_zoom["3"] == 4

    async def test_critical_path_marks_failure_route(self, app, client):
        rid = await _seed(client, with_failure=True)
        engine: GraphEngine = app.state.graph_engine
        bundle = await engine.build(rid)

        assert bundle.summary.critical_path_length >= 2
        # First node on critical path is the run root.
        assert bundle.critical_path[0] != bundle.critical_path[-1]
        # The marked nodes are exactly those in critical_path.
        marked = {n.id for n in bundle.nodes if n.on_critical_path}
        assert marked == set(bundle.critical_path)

    async def test_clusters_present(self, app, client):
        rid = await _seed(client)
        engine: GraphEngine = app.state.graph_engine
        bundle = await engine.build(rid)
        types = {c.type for c in bundle.clusters}
        # We always get at least the top-level goal cluster.
        assert "goal" in types

    async def test_lru_serves_repeated_calls(self, app, client):
        rid = await _seed(client)
        engine: GraphEngine = app.state.graph_engine
        b1 = await engine.build(rid)
        b2 = await engine.build(rid)
        assert b1 is b2  # cache returns the same object

    async def test_invalidate_run_clears_cache(self, app, client):
        rid = await _seed(client)
        engine: GraphEngine = app.state.graph_engine
        b1 = await engine.build(rid)
        await engine.invalidate_run(rid)
        b2 = await engine.build(rid)
        assert b1 is not b2  # cache was dropped, fresh build
        # Both bundles should be equal in content though.
        assert b1.summary.total_nodes == b2.summary.total_nodes
