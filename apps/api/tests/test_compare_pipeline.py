"""End-to-end tests for the comparative debugger (substeps 4.1-4.4)."""

from __future__ import annotations

import uuid

import pytest
from reverie_schema import (
    CognitiveEvent,
    GoalPayload,
    RetryPayload,
    ToolPayload,
)

from reverie_api.compare.align import align_runs
from reverie_api.compare.diff import compute_diff
from reverie_api.compare.fault_tree import build_fault_tree


def _new_id() -> str:
    return str(uuid.uuid4())


def _evt(
    type_: str,
    payload,
    *,
    parent_id: str | None = None,
    ts: int = 0,
    event_id: str | None = None,
) -> CognitiveEvent:
    return CognitiveEvent(
        id=event_id or _new_id(),
        type=type_,
        run_id="11111111-1111-4111-8111-111111111111",
        session_id="22222222-2222-4222-8222-222222222222",
        agent_id="agent-test",
        parent_id=parent_id,
        depth=0,
        timestamp=ts,
        duration_ms=None,
        payload=payload,
    )


def _tool(
    name: str = "x",
    *,
    type_: str = "tool.called",
    success: bool = True,
    token_cost: int | None = None,
    error: str | None = None,
    parent_id: str | None = None,
    ts: int = 0,
    event_id: str | None = None,
) -> CognitiveEvent:
    return _evt(
        type_,
        ToolPayload(
            tool_name=name, args={"q": "x"}, result=None,
            latency_ms=0.0, token_cost=token_cost, success=success, error_message=error,
        ),
        parent_id=parent_id, ts=ts, event_id=event_id,
    )


def _goal(intent: str = "x", *, parent_id: str | None = None, ts: int = 0) -> CognitiveEvent:
    return _evt(
        "goal.created",
        GoalPayload(intent=intent, priority="high", context=""),
        parent_id=parent_id, ts=ts,
    )


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


class TestDiff:
    def test_identical_runs_have_no_divergence(self):
        a = [_goal(ts=0), _tool("search", ts=1)]
        b = [_goal(ts=0), _tool("search", ts=1)]
        diff = compute_diff(
            run_a_id="A", run_b_id="B",
            events_a=a, events_b=b,
            alignment=align_runs(a, b),
        )
        assert diff.divergence is None

    def test_extra_retries_in_b_show_up(self):
        a = [_goal(ts=0), _tool("search", ts=1)]
        retry_evt = _evt(
            "retry.triggered",
            RetryPayload(reason="x", attempt=1, max_attempts=3, previous_error="y", backoff_ms=0.0),
            ts=2,
        )
        b = [_goal(ts=0), _tool("search", ts=1), retry_evt]
        diff = compute_diff(
            run_a_id="A", run_b_id="B",
            events_a=a, events_b=b,
            alignment=align_runs(a, b),
        )
        assert diff.retries_in_a == 0
        assert diff.retries_in_b == 1

    def test_token_delta_is_b_minus_a(self):
        a = [_tool("x", type_="tool.returned", token_cost=100, ts=0)]
        b = [_tool("x", type_="tool.returned", token_cost=300, ts=0)]
        diff = compute_diff(
            run_a_id="A", run_b_id="B",
            events_a=a, events_b=b,
            alignment=align_runs(a, b),
        )
        assert diff.token_delta == 200

    def test_extra_tool_in_b_listed(self):
        a = [_tool("alpha", ts=0)]
        b = [_tool("alpha", ts=0), _tool("beta", ts=1)]
        diff = compute_diff(
            run_a_id="A", run_b_id="B",
            events_a=a, events_b=b,
            alignment=align_runs(a, b),
        )
        assert "beta" in diff.extra_tools_in_b
        assert "alpha" not in diff.extra_tools_in_b

    def test_failure_count_distinguishes_runs(self):
        a = [_goal(ts=0)]
        fail = _tool("x", type_="tool.failed", success=False, error="boom", ts=0)
        b = [_goal(ts=0), fail]
        diff = compute_diff(
            run_a_id="A", run_b_id="B",
            events_a=a, events_b=b,
            alignment=align_runs(a, b),
        )
        assert diff.failures_in_a == 0
        assert diff.failures_in_b == 1

    def test_divergence_first_only_pair(self):
        a = [_tool("a", ts=0)]
        b = [_tool("a", ts=0), _tool("b", ts=1)]
        diff = compute_diff(
            run_a_id="A", run_b_id="B",
            events_a=a, events_b=b,
            alignment=align_runs(a, b),
        )
        assert diff.divergence is not None
        assert diff.divergence.reason.startswith("event present in B")


# ---------------------------------------------------------------------------
# Fault tree
# ---------------------------------------------------------------------------


class TestFaultTree:
    def test_walks_back_to_root(self):
        root = _goal("mission", ts=0)
        sub = _goal("subtask", parent_id=root.id, ts=1)
        fail = _tool("bad", type_="tool.failed", success=False,
                     error="boom", parent_id=sub.id, ts=2)
        tree = build_fault_tree(failure_event=fail, events=[root, sub, fail])
        assert tree.failure_event_id == fail.id
        assert tree.root_event_id == root.id
        assert tree.chain_event_ids == [root.id, sub.id, fail.id]

    def test_orphan_failure_just_returns_self(self):
        ghost_parent = _new_id()
        fail = _tool("bad", type_="tool.failed", success=False, error="x")
        # Build a fail event that points at a non-existent parent.
        fail = fail.model_copy(update={"parent_id": ghost_parent})
        tree = build_fault_tree(failure_event=fail, events=[fail])
        assert tree.chain_event_ids == [fail.id]
        # The first-and-only entry in the chain IS the root for this orphan.
        assert tree.root_event_id == fail.id


# ---------------------------------------------------------------------------
# Compare engine via CompareEngine.compare()
# ---------------------------------------------------------------------------


from .conftest import (
    goal_event,
    make_event,
    make_run_create,
    tool_returned_event,
)


async def _seed_pair(client) -> tuple[str, str]:
    """Seed two runs that share a goal but diverge on the second tool call."""

    async def _seed_one(token_cost: int, with_failure: bool):
        body = make_run_create()
        await client.post("/api/v1/runs", json=body)
        rid = body["runId"]
        g = goal_event(rid, depth=0, timestamp=0)
        events = [g]
        # Same tool call in both runs.
        events.append(
            make_event(rid, parentId=g["id"], depth=1, timestamp=1, payload={
                "_type": "tool", "toolName": "search", "args": {"q": "x"},
                "result": None, "latencyMs": 1.0, "tokenCost": None,
                "success": True, "errorMessage": None,
            })
        )
        events.append(
            tool_returned_event(rid, parentId=g["id"], depth=1, timestamp=2, token_cost=token_cost)
        )
        if with_failure:
            events.append(make_event(
                rid,
                event_type="tool.failed",
                parentId=g["id"], depth=1, timestamp=3,
                payload={
                    "_type": "tool", "toolName": "next_step",
                    "args": {}, "result": None, "latencyMs": 0.0,
                    "tokenCost": None, "success": False, "errorMessage": "boom",
                },
            ))
        await client.post("/api/v1/events/batch", json=events)
        return rid

    # Run A succeeds with light tokens; Run B fails after the same setup.
    rid_a = await _seed_one(token_cost=10, with_failure=False)
    rid_b = await _seed_one(token_cost=30, with_failure=True)
    return rid_a, rid_b


class TestCompareEngine:
    async def test_compare_returns_full_result(self, app, client):
        rid_a, rid_b = await _seed_pair(client)
        engine = app.state.compare_engine
        result = await engine.compare(rid_a, rid_b, with_narrative=False)

        assert result.diff.run_a_id == rid_a
        assert result.diff.run_b_id == rid_b
        # Token delta is positive: B used more.
        assert result.diff.token_delta > 0
        # B has a failure; A doesn't.
        assert result.diff.failures_in_a == 0
        assert result.diff.failures_in_b == 1
        # Fault tree only on B.
        assert result.fault_tree_a is None
        assert result.fault_tree_b is not None

    async def test_compare_without_narrative_skips_status(self, app, client):
        rid_a, rid_b = await _seed_pair(client)
        engine = app.state.compare_engine
        result = await engine.compare(rid_a, rid_b, with_narrative=False)
        assert result.narrative_status == "skipped"

    async def test_unknown_run_a_raises(self, app, client):
        from reverie_api.db import RunNotFoundError

        rid_a, rid_b = await _seed_pair(client)
        engine = app.state.compare_engine
        with pytest.raises(RunNotFoundError):
            await engine.compare("00000000-0000-4000-8000-000000000000", rid_b)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


class TestCompareRoute:
    async def test_post_returns_full_diff(self, client):
        rid_a, rid_b = await _seed_pair(client)
        r = await client.post(
            "/api/v1/compare?with_narrative=false",
            json={"runAId": rid_a, "runBId": rid_b},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["diff"]["runAId"] == rid_a
        assert body["diff"]["runBId"] == rid_b
        assert "alignment" in body
        assert "narrativeStatus" in body
        # Failures in B but not A.
        assert body["diff"]["failuresInB"] == 1
        assert body["diff"]["failuresInA"] == 0
        # Fault tree on B only.
        assert body["faultTreeB"] is not None
        assert body["faultTreeA"] is None

    async def test_missing_run_id_returns_400(self, client):
        r = await client.post("/api/v1/compare", json={"runAId": "x"})
        assert r.status_code == 400

    async def test_unknown_run_returns_404(self, client):
        rid_a, _ = await _seed_pair(client)
        r = await client.post(
            "/api/v1/compare",
            json={"runAId": rid_a, "runBId": "00000000-0000-4000-8000-000000000000"},
        )
        assert r.status_code == 404
