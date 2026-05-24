"""Tests for the graph builder + zoom assignment (substep 2.1).

Pure-function tests — no DB. Anomaly/cluster/critical-path machinery is
stubbed at this point and tested in 2.2/2.3.
"""

from __future__ import annotations

import uuid

from reverie_schema import (
    CognitiveEvent,
    ContextPayload,
    GoalPayload,
    MemoryPayload,
    PlannerPayload,
    ReasoningPayload,
    RetryPayload,
    SubagentPayload,
    ToolPayload,
    ValidationPayload,
)

from reverie_api.graph.build import build_nodes_and_edges
from reverie_api.graph.zoom import assign_zoom


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
    timestamp: int = 1_700_000_000_000,
    duration_ms: float | None = None,
    salience: float | None = None,
    anomaly: bool = False,
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
        duration_ms=duration_ms,
        payload=payload,
        salience=salience,
        anomaly=anomaly,
    )


def _goal(intent: str = "do x", *, depth: int = 0, **kw) -> CognitiveEvent:
    return _evt(
        "goal.created",
        GoalPayload(intent=intent, priority="high", context=""),
        depth=depth,
        **kw,
    )


def _tool(name: str = "search", *, depth: int = 1, **kw) -> CognitiveEvent:
    return _evt(
        "tool.called",
        ToolPayload(
            tool_name=name,
            args={"q": "x"},
            result=None,
            latency_ms=0.0,
            token_cost=None,
            success=True,
            error_message=None,
        ),
        depth=depth,
        **kw,
    )


# ---------------------------------------------------------------------------
# assign_zoom
# ---------------------------------------------------------------------------


class TestAssignZoom:
    def test_root_goal_is_l1(self):
        e = _goal("mission", depth=0)
        assert assign_zoom(e) == 1

    def test_depth_1_goal_is_l2(self):
        e = _goal("subtask", depth=1)
        assert assign_zoom(e) == 2

    def test_deep_goal_falls_to_l3(self):
        e = _goal("nested", depth=3)
        assert assign_zoom(e) == 3

    def test_subagent_spawned_is_l2(self):
        e = _evt(
            "subagent.spawned",
            SubagentPayload(agent_type="r", task="t", delegated_goal_id=None, child_run_id=None),
        )
        assert assign_zoom(e) == 2

    def test_goal_completed_is_l2(self):
        e = _evt("goal.completed", GoalPayload(intent="done", priority="high", context=""))
        assert assign_zoom(e) == 2

    def test_goal_failed_is_l2(self):
        e = _evt("goal.failed", GoalPayload(intent="oh no", priority="high", context="boom"))
        assert assign_zoom(e) == 2

    def test_tool_called_is_l3(self):
        assert assign_zoom(_tool()) == 3

    def test_tool_returned_is_l3(self):
        e = _evt(
            "tool.returned",
            ToolPayload(
                tool_name="x", args={}, result=None,
                latency_ms=0.0, token_cost=None, success=True, error_message=None,
            ),
        )
        assert assign_zoom(e) == 3

    def test_tool_failed_is_l3(self):
        e = _evt(
            "tool.failed",
            ToolPayload(
                tool_name="x", args={}, result=None,
                latency_ms=0.0, token_cost=None, success=False, error_message="boom",
            ),
        )
        assert assign_zoom(e) == 3

    def test_memory_retrieved_is_l3(self):
        e = _evt(
            "memory.retrieved",
            MemoryPayload(query="q", hit_count=1, relevance_scores=[0.9], retrieval_ms=1.0, storage_key=None),
        )
        assert assign_zoom(e) == 3

    def test_validation_failed_is_l3(self):
        e = _evt(
            "validation.failed",
            ValidationPayload(check_name="c", passed=False, severity="error", details=""),
        )
        assert assign_zoom(e) == 3

    def test_retry_triggered_is_l4(self):
        e = _evt(
            "retry.triggered",
            RetryPayload(reason="x", attempt=1, max_attempts=3, previous_error="y", backoff_ms=0.0),
        )
        assert assign_zoom(e) == 4

    def test_validation_passed_is_l4(self):
        e = _evt(
            "validation.passed",
            ValidationPayload(check_name="c", passed=True, severity="info", details=""),
        )
        assert assign_zoom(e) == 4

    def test_reasoning_extracted_is_l4(self):
        e = _evt(
            "reasoning.extracted",
            ReasoningPayload(raw_text=None, summary="s", model_id="x", tokens_used=10),
        )
        assert assign_zoom(e) == 4

    def test_context_truncated_is_l4(self):
        e = _evt(
            "context.truncated",
            ContextPayload(tokens_used=5, token_limit=10, percent_used=50.0, truncated_messages=1),
        )
        assert assign_zoom(e) == 4

    def test_planner_updated_is_l4(self):
        e = _evt(
            "planner.updated",
            PlannerPayload(plan="p", step=1, total_steps=3, revision=0),
        )
        assert assign_zoom(e) == 4

    def test_zoom_levels_progress_monotonically(self):
        """A 500-event mix should produce the SRS-predicted distribution
        (lots of L4, fewer L3, even fewer L2, very few L1).
        """

        events: list[CognitiveEvent] = [_goal("mission")]  # 1 L1
        # Add a bunch of L4-grade noise + L3 tool calls.
        for i in range(200):
            events.append(_tool(f"t{i}", depth=2, timestamp=i))
        for i in range(300):
            events.append(
                _evt(
                    "retry.triggered",
                    RetryPayload(
                        reason="x",
                        attempt=1,
                        max_attempts=3,
                        previous_error="y",
                        backoff_ms=0.0,
                    ),
                    depth=3,
                    timestamp=i,
                )
            )

        per_zoom = {1: 0, 2: 0, 3: 0, 4: 0}
        for e in events:
            per_zoom[int(assign_zoom(e))] += 1

        assert per_zoom[1] == 1
        assert per_zoom[3] >= 200
        assert per_zoom[4] >= 300
        # Sanity: L1 << L3 << L4 for a typical operational trace.
        assert per_zoom[1] < per_zoom[3] < per_zoom[4]


# ---------------------------------------------------------------------------
# build_nodes_and_edges
# ---------------------------------------------------------------------------


class TestBuildNodesAndEdges:
    def test_empty_event_list_produces_empty_graph(self):
        nodes, edges = build_nodes_and_edges([])
        assert nodes == []
        assert edges == []

    def test_single_root_event_has_no_edges(self):
        e = _goal("mission")
        nodes, edges = build_nodes_and_edges([e])
        assert len(nodes) == 1
        assert nodes[0].id == e.id
        assert nodes[0].zoom_level == 1
        assert nodes[0].parent_id is None
        assert edges == []

    def test_parent_child_pair_makes_one_edge(self):
        root = _goal("mission")
        child = _tool(name="search", depth=1, parent_id=root.id, timestamp=2)
        nodes, edges = build_nodes_and_edges([root, child])

        assert len(nodes) == 2
        assert len(edges) == 1
        assert edges[0].source == root.id
        assert edges[0].target == child.id

    def test_orphan_parent_id_is_skipped(self):
        # parent_id points to an event we don't have.
        ghost_parent = _new_id()
        child = _tool(name="x", depth=1, parent_id=ghost_parent)
        nodes, edges = build_nodes_and_edges([child])
        assert len(nodes) == 1
        assert edges == []  # orphan reference is silently dropped

    def test_three_level_tree(self):
        root = _goal("mission")
        sub = _goal("subtask", depth=1, parent_id=root.id, timestamp=2)
        leaf = _tool(name="search", depth=2, parent_id=sub.id, timestamp=3)
        nodes, edges = build_nodes_and_edges([root, sub, leaf])

        assert len(nodes) == 3
        # Edges in walk order.
        sources = {(e.source, e.target) for e in edges}
        assert (root.id, sub.id) in sources
        assert (sub.id, leaf.id) in sources

    def test_label_is_compact(self):
        root = _goal("research the current state of agent observability tools" * 5)
        nodes, _ = build_nodes_and_edges([root])
        # _label trims to <=80 chars + ellipsis.
        assert len(nodes[0].label) <= 81

    def test_anomaly_flag_propagates_from_event(self):
        # The schema-level boolean (event.anomaly) must show up on the node
        # even before any anomaly detector runs.
        e = _goal("x", anomaly=True)
        nodes, _ = build_nodes_and_edges([e])
        assert nodes[0].anomaly is True

    def test_node_carries_timing_metadata(self):
        e = _evt(
            "tool.returned",
            ToolPayload(
                tool_name="x", args={}, result=None,
                latency_ms=42.5, token_cost=None, success=True, error_message=None,
            ),
            duration_ms=42.5,
            timestamp=1_700_000_000_999,
        )
        nodes, _ = build_nodes_and_edges([e])
        assert nodes[0].duration_ms == 42.5
        assert nodes[0].timestamp == 1_700_000_000_999


# ---------------------------------------------------------------------------
# Wire format
# ---------------------------------------------------------------------------


class TestWireFormat:
    def test_node_dump_uses_camelcase(self):
        e = _tool(name="x", parent_id="p", depth=1, duration_ms=1.0)
        nodes, _ = build_nodes_and_edges([e])
        wire = nodes[0].model_dump(by_alias=True)
        for key in ("parentId", "zoomLevel", "durationMs", "onCriticalPath"):
            assert key in wire
        for forbidden in ("parent_id", "zoom_level", "duration_ms", "on_critical_path"):
            assert forbidden not in wire

    def test_edge_dump_uses_camelcase(self):
        root = _goal("a")
        child = _tool(parent_id=root.id, depth=1, timestamp=2)
        _, edges = build_nodes_and_edges([root, child])
        wire = edges[0].model_dump(by_alias=True)
        assert "source" in wire
        assert "target" in wire
        assert "onCriticalPath" in wire
