"""Tests for the six anomaly detectors (substep 2.2)."""

from __future__ import annotations

import uuid
from typing import Any

from reverie_schema import (
    CognitiveEvent,
    GoalPayload,
    MemoryPayload,
    ReasoningPayload,
    SubagentPayload,
    ToolPayload,
)

from reverie_api.graph.anomalies import (
    ABANDON_SECONDS,
    BOTTLENECK_LATENCY_MULT,
    EXPLOSION_CHILD_COUNT,
    HOTSPOT_TOKEN_PCT,
    LOOP_WINDOW_MS,
    POISON_HIT_COUNT,
    POISON_RELEVANCE_THRESHOLD,
    annotate_anomalies,
)
from reverie_api.graph.build import build_nodes_and_edges


RUN_ID = "11111111-1111-4111-8111-111111111111"


def _new_id() -> str:
    return str(uuid.uuid4())


def _evt(
    type_: str,
    payload: Any,
    *,
    event_id: str | None = None,
    parent_id: str | None = None,
    depth: int = 0,
    timestamp: int = 1_700_000_000_000,
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


def _tool_called(name: str, args: dict[str, Any] | None = None, *, ts: int = 1) -> CognitiveEvent:
    return _evt(
        "tool.called",
        ToolPayload(
            tool_name=name,
            args=args or {"q": "x"},
            result=None,
            latency_ms=0.0,
            token_cost=None,
            success=True,
            error_message=None,
        ),
        timestamp=ts,
    )


def _tool_returned(
    name: str = "x",
    *,
    ts: int = 1,
    latency_ms: float = 10.0,
    token_cost: int | None = None,
) -> CognitiveEvent:
    return _evt(
        "tool.returned",
        ToolPayload(
            tool_name=name,
            args={"q": "x"},
            result={"ok": True},
            latency_ms=latency_ms,
            token_cost=token_cost,
            success=True,
            error_message=None,
        ),
        timestamp=ts,
    )


def _kinds(node) -> list[str]:
    return [a.kind for a in node.anomalies]


def _by_id(nodes):
    return {n.id: n for n in nodes}


# ---------------------------------------------------------------------------
# LOOP
# ---------------------------------------------------------------------------


class TestLoop:
    def test_two_identical_calls_within_window_flag_both(self):
        a = _tool_called("search", {"q": "x"}, ts=0)
        b = _tool_called("search", {"q": "x"}, ts=LOOP_WINDOW_MS - 1)
        events = [a, b]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        index = _by_id(nodes)
        assert "loop" in _kinds(index[a.id])
        assert "loop" in _kinds(index[b.id])

    def test_calls_outside_window_are_not_flagged(self):
        a = _tool_called("search", {"q": "x"}, ts=0)
        b = _tool_called("search", {"q": "x"}, ts=LOOP_WINDOW_MS + 1)
        events = [a, b]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        index = _by_id(nodes)
        assert "loop" not in _kinds(index[a.id])
        assert "loop" not in _kinds(index[b.id])

    def test_different_args_are_not_a_loop(self):
        a = _tool_called("search", {"q": "x"}, ts=0)
        b = _tool_called("search", {"q": "y"}, ts=10)
        events = [a, b]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        index = _by_id(nodes)
        assert "loop" not in _kinds(index[a.id])
        assert "loop" not in _kinds(index[b.id])

    def test_args_dict_order_does_not_matter(self):
        a = _tool_called("search", {"q": "x", "limit": 10}, ts=0)
        b = _tool_called("search", {"limit": 10, "q": "x"}, ts=10)
        events = [a, b]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        index = _by_id(nodes)
        assert "loop" in _kinds(index[a.id])
        assert "loop" in _kinds(index[b.id])

    def test_three_calls_only_flag_each_once(self):
        ids = [_tool_called("x", ts=t) for t in (0, 100, 200)]
        nodes, _ = build_nodes_and_edges(ids)
        annotate_anomalies(nodes, ids)
        for n in nodes:
            assert _kinds(n).count("loop") == 1


# ---------------------------------------------------------------------------
# HOTSPOT
# ---------------------------------------------------------------------------


class TestHotspot:
    def test_dominant_token_node_is_flagged(self):
        a = _tool_returned("a", token_cost=80, ts=0)
        b = _tool_returned("b", token_cost=10, ts=1)
        c = _tool_returned("c", token_cost=10, ts=2)
        events = [a, b, c]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        index = _by_id(nodes)
        # 80 / 100 = 80% — well over 20%
        assert "hotspot" in _kinds(index[a.id])
        assert "hotspot" not in _kinds(index[b.id])
        assert "hotspot" not in _kinds(index[c.id])

    def test_below_threshold_is_not_flagged(self):
        # Each of 100 nodes contributes 1% of total → no hotspot.
        events = [
            _tool_returned(f"t{i}", token_cost=1, ts=i) for i in range(100)
        ]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        for n in nodes:
            assert "hotspot" not in _kinds(n)

    def test_at_threshold_is_flagged(self):
        # Each of 5 nodes contributes 20% — at the inclusive boundary,
        # which we flag.
        events = [
            _tool_returned(f"t{i}", token_cost=20, ts=i) for i in range(5)
        ]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        for n in nodes:
            assert "hotspot" in _kinds(n)
        # Pin the constant so the SRS link stays explicit.
        assert HOTSPOT_TOKEN_PCT == 0.20

    def test_no_tokens_anywhere_means_no_hotspot(self):
        events = [_tool_returned(f"t{i}", token_cost=None, ts=i) for i in range(3)]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        for n in nodes:
            assert "hotspot" not in _kinds(n)

    def test_reasoning_tokens_counted(self):
        big = _evt(
            "reasoning.extracted",
            ReasoningPayload(raw_text=None, summary="s", model_id="m", tokens_used=900),
            timestamp=1,
        )
        small = _tool_returned("t", token_cost=100, ts=2)
        events = [big, small]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        index = _by_id(nodes)
        assert "hotspot" in _kinds(index[big.id])


# ---------------------------------------------------------------------------
# BOTTLENECK
# ---------------------------------------------------------------------------


class TestBottleneck:
    def test_3x_median_flagged(self):
        # Median 10ms; the 50ms node is 5x → flagged.
        events = [
            _tool_returned("a", latency_ms=10.0, ts=0),
            _tool_returned("b", latency_ms=10.0, ts=1),
            _tool_returned("c", latency_ms=10.0, ts=2),
            _tool_returned("d", latency_ms=50.0, ts=3),
        ]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        index = _by_id(nodes)
        assert "bottleneck" in _kinds(index[events[3].id])

    def test_just_below_threshold_not_flagged(self):
        # Median 10; 29ms is 2.9x < 3x → not flagged.
        events = [
            _tool_returned("a", latency_ms=10.0, ts=0),
            _tool_returned("b", latency_ms=10.0, ts=1),
            _tool_returned("c", latency_ms=29.0, ts=2),
        ]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        index = _by_id(nodes)
        assert "bottleneck" not in _kinds(index[events[2].id])
        assert BOTTLENECK_LATENCY_MULT == 3.0  # constant pinned

    def test_too_few_samples_short_circuits(self):
        events = [_tool_returned("a", latency_ms=999.0, ts=0)]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        # With only one sample the detector cannot compute a meaningful median.
        for n in nodes:
            assert "bottleneck" not in _kinds(n)


# ---------------------------------------------------------------------------
# POISON
# ---------------------------------------------------------------------------


class TestPoison:
    def test_three_low_relevance_retrievals_flag_all(self):
        events = [
            _evt(
                "memory.retrieved",
                MemoryPayload(
                    query="q",
                    hit_count=1,
                    relevance_scores=[0.05],
                    retrieval_ms=1.0,
                    storage_key="k",
                ),
                timestamp=i,
            )
            for i in range(POISON_HIT_COUNT)
        ]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        for n in nodes:
            assert "poison" in _kinds(n)

    def test_one_strong_score_resets_nothing_but_avoids_flag(self):
        events = [
            _evt(
                "memory.retrieved",
                MemoryPayload(
                    query="q",
                    hit_count=1,
                    relevance_scores=[0.05, 0.9],  # max is 0.9 → strong
                    retrieval_ms=1.0,
                    storage_key="k",
                ),
                timestamp=1,
            )
        ]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        for n in nodes:
            assert "poison" not in _kinds(n)

    def test_threshold_constants_match_srs(self):
        assert POISON_RELEVANCE_THRESHOLD == 0.10
        assert POISON_HIT_COUNT == 3


# ---------------------------------------------------------------------------
# EXPLOSION
# ---------------------------------------------------------------------------


class TestExplosion:
    def test_more_than_eight_children_flags_parent(self):
        parent = _evt(
            "subagent.spawned",
            SubagentPayload(agent_type="r", task="t", delegated_goal_id=None, child_run_id=None),
            timestamp=0,
        )
        children = [
            _evt(
                "subagent.spawned",
                SubagentPayload(agent_type=f"c{i}", task="t", delegated_goal_id=None, child_run_id=None),
                parent_id=parent.id,
                timestamp=1 + i,
            )
            for i in range(EXPLOSION_CHILD_COUNT + 1)
        ]
        events = [parent, *children]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        index = _by_id(nodes)
        assert "explosion" in _kinds(index[parent.id])

    def test_at_or_below_threshold_no_flag(self):
        parent = _evt(
            "subagent.spawned",
            SubagentPayload(agent_type="r", task="t", delegated_goal_id=None, child_run_id=None),
            timestamp=0,
        )
        children = [
            _evt(
                "subagent.spawned",
                SubagentPayload(agent_type=f"c{i}", task="t", delegated_goal_id=None, child_run_id=None),
                parent_id=parent.id,
                timestamp=1 + i,
            )
            for i in range(EXPLOSION_CHILD_COUNT)  # exactly 8
        ]
        events = [parent, *children]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        index = _by_id(nodes)
        assert "explosion" not in _kinds(index[parent.id])


# ---------------------------------------------------------------------------
# ABANDON
# ---------------------------------------------------------------------------


class TestAbandon:
    def test_goal_with_no_children_after_window_flagged(self):
        goal = _evt(
            "goal.created",
            GoalPayload(intent="g", priority="high", context=""),
            timestamp=0,
        )
        # Some unrelated event happens far in the future to define "now".
        recent = _tool_returned("u", ts=ABANDON_SECONDS * 1000 + 1)
        events = [goal, recent]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        index = _by_id(nodes)
        assert "abandon" in _kinds(index[goal.id])

    def test_completed_goal_is_not_abandoned(self):
        goal = _evt(
            "goal.created",
            GoalPayload(intent="g", priority="high", context=""),
            timestamp=0,
        )
        completion = _evt(
            "goal.completed",
            GoalPayload(intent="g", priority="high", context=""),
            parent_id=goal.id,  # parent-link end convention
            timestamp=1,
        )
        recent = _tool_returned("u", ts=ABANDON_SECONDS * 1000 + 100)
        events = [goal, completion, recent]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        index = _by_id(nodes)
        assert "abandon" not in _kinds(index[goal.id])

    def test_recently_active_goal_not_flagged(self):
        goal = _evt(
            "goal.created",
            GoalPayload(intent="g", priority="high", context=""),
            timestamp=0,
        )
        # Active just now.
        recent = _tool_returned("u", ts=10)
        events = [goal, recent]
        nodes, _ = build_nodes_and_edges(events)
        annotate_anomalies(nodes, events)
        index = _by_id(nodes)
        assert "abandon" not in _kinds(index[goal.id])
