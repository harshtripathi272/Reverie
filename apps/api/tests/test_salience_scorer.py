"""Tests for the pure salience scorer (substep 3.1)."""

from __future__ import annotations

import uuid

from reverie_schema import (
    CognitiveEvent,
    GoalPayload,
    ToolPayload,
)

from reverie_api.graph.anomalies import annotate_anomalies
from reverie_api.graph.build import build_nodes_and_edges
from reverie_api.graph.types import (
    AnomalyAnnotation,
    GraphBundle,
    GraphSummary,
)
from reverie_api.salience import (
    SALIENCE_NOISE_THRESHOLD,
    SalienceConfig,
    score_salience,
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
):
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


def _bundle(events, *, critical_path: list[str] | None = None) -> GraphBundle:
    nodes, edges = build_nodes_and_edges(events)
    annotate_anomalies(nodes, events)
    if critical_path is None:
        critical_path = []
    return GraphBundle(
        run_id=RUN_ID,
        nodes=nodes,
        edges=edges,
        clusters=[],
        critical_path=critical_path,
        summary=GraphSummary(
            total_nodes=len(nodes),
            total_edges=len(edges),
            nodes_per_zoom={"1": 0, "2": 0, "3": 0, "4": 0},
            anomalies_by_kind={},
            critical_path_length=len(critical_path),
        ),
    )


# ---------------------------------------------------------------------------
# Per-component tests
# ---------------------------------------------------------------------------


class TestScoreComponents:
    def test_empty_bundle_does_nothing(self):
        b = _bundle([])
        score_salience(b)
        assert b.nodes == []

    def test_critical_path_only(self):
        # One root goal; just being on the critical path → 0.30.
        # Single-node run has no recency ramp (n_nodes - 1 = 0), so we expect
        # exactly 0.30.
        e = _evt("goal.created", GoalPayload(intent="m", priority="high", context=""))
        b = _bundle([e], critical_path=[e.id])
        score_salience(b)
        assert b.nodes[0].salience == 0.30

    def test_anomaly_alone_scores_anomaly_weight(self):
        e = _evt("goal.created", GoalPayload(intent="m", priority="high", context=""))
        b = _bundle([e])
        # Manually add an anomaly so the scorer has something to find.
        b.nodes[0].anomalies.append(
            AnomalyAnnotation(kind="loop", severity="warning", detail="x")
        )
        score_salience(b)
        assert b.nodes[0].salience == 0.20

    def test_failure_event_scores_failure_weight(self):
        e = _evt(
            "tool.failed",
            ToolPayload(
                tool_name="x", args={}, result=None,
                latency_ms=0.0, token_cost=None, success=False, error_message="boom",
            ),
        )
        b = _bundle([e])
        score_salience(b)
        # tool.failed → +0.20 (failure)
        assert b.nodes[0].salience == 0.20

    def test_retry_trigger_scores_retry_weight(self):
        from reverie_schema import RetryPayload

        e = _evt(
            "retry.triggered",
            RetryPayload(
                reason="x", attempt=1, max_attempts=3,
                previous_error="y", backoff_ms=0.0,
            ),
        )
        b = _bundle([e])
        score_salience(b)
        assert b.nodes[0].salience == 0.10

    def test_hotspot_anomaly_adds_hot_token_bonus(self):
        e = _evt("goal.created", GoalPayload(intent="m", priority="high", context=""))
        b = _bundle([e])
        b.nodes[0].anomalies.append(
            AnomalyAnnotation(kind="hotspot", severity="warning", detail="50% tokens")
        )
        score_salience(b)
        # anomaly (0.20) + hotspot bonus (0.15) = 0.35
        assert b.nodes[0].salience == 0.35

    def test_combined_failure_and_critical_path(self):
        e = _evt(
            "tool.failed",
            ToolPayload(
                tool_name="x", args={}, result=None,
                latency_ms=0.0, token_cost=None, success=False, error_message="boom",
            ),
        )
        b = _bundle([e], critical_path=[e.id])
        score_salience(b)
        # 0.30 (critical) + 0.20 (failure) = 0.50
        assert b.nodes[0].salience == 0.50

    def test_recency_ramps_linearly(self):
        # Three events at increasing timestamps; only recency contributes.
        e1 = _evt("goal.created", GoalPayload(intent="a", priority="high", context=""), timestamp=1)
        e2 = _evt("goal.created", GoalPayload(intent="b", priority="high", context=""), timestamp=2)
        e3 = _evt("goal.created", GoalPayload(intent="c", priority="high", context=""), timestamp=3)
        b = _bundle([e1, e2, e3])
        score_salience(b)
        # Oldest gets 0.00, middle 0.025, newest 0.05.
        salience_by_id = {n.id: n.salience for n in b.nodes}
        assert salience_by_id[e1.id] == 0.0
        assert salience_by_id[e2.id] == 0.025
        assert salience_by_id[e3.id] == 0.05


# ---------------------------------------------------------------------------
# Bounds + idempotency
# ---------------------------------------------------------------------------


class TestBoundsAndIdempotency:
    def test_score_clamps_to_one(self):
        # Stack every signal: critical + anomaly + failure + hot + recency
        # = 0.30 + 0.20 + 0.20 + 0.15 + 0.05 = 0.90; +retry 0.10 → 1.00.
        from reverie_schema import RetryPayload

        # We can't have a single event that's BOTH a tool.failed AND a
        # retry.triggered. Build two events; verify NO node ever exceeds 1.0.
        e1 = _evt(
            "tool.failed",
            ToolPayload(
                tool_name="x", args={}, result=None,
                latency_ms=0.0, token_cost=None, success=False, error_message="boom",
            ),
            timestamp=1,
        )
        e2 = _evt(
            "retry.triggered",
            RetryPayload(reason="x", attempt=1, max_attempts=3, previous_error="y", backoff_ms=0.0),
            timestamp=2,
        )
        b = _bundle([e1, e2], critical_path=[e1.id, e2.id])
        b.nodes[0].anomalies.append(AnomalyAnnotation(kind="hotspot", severity="warning", detail="x"))
        b.nodes[1].anomalies.append(AnomalyAnnotation(kind="hotspot", severity="warning", detail="x"))
        score_salience(b)
        for n in b.nodes:
            assert 0.0 <= n.salience <= 1.0

    def test_running_twice_produces_same_score(self):
        e = _evt("goal.created", GoalPayload(intent="m", priority="high", context=""))
        b = _bundle([e], critical_path=[e.id])
        score_salience(b)
        first = b.nodes[0].salience
        score_salience(b)
        assert b.nodes[0].salience == first


# ---------------------------------------------------------------------------
# Configurability
# ---------------------------------------------------------------------------


class TestConfigurability:
    def test_custom_weights_override(self):
        e = _evt("goal.created", GoalPayload(intent="m", priority="high", context=""))
        b = _bundle([e], critical_path=[e.id])
        cfg = SalienceConfig(critical_path_weight=1.0)
        score_salience(b, config=cfg)
        assert b.nodes[0].salience == 1.0

    def test_noise_threshold_constant_is_pinned(self):
        # Documented in the SRS at 0.10. Don't change without bumping the
        # frontend's filter logic too.
        assert SALIENCE_NOISE_THRESHOLD == 0.10
