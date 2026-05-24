"""Tests for the Needleman-Wunsch alignment (substep 4.1)."""

from __future__ import annotations

import uuid

from reverie_schema import (
    CognitiveEvent,
    GoalPayload,
    ToolPayload,
)

from reverie_api.compare.align import (
    AlignmentConfig,
    align_runs,
    event_similarity,
)


def _new_id() -> str:
    return str(uuid.uuid4())


def _evt(type_: str, payload, *, ts: int = 0) -> CognitiveEvent:
    return CognitiveEvent(
        id=_new_id(),
        type=type_,
        run_id="11111111-1111-4111-8111-111111111111",
        session_id="22222222-2222-4222-8222-222222222222",
        agent_id="agent-test",
        parent_id=None,
        depth=0,
        timestamp=ts,
        duration_ms=None,
        payload=payload,
    )


def _tool(name: str, *, type_: str = "tool.called", success: bool = True) -> CognitiveEvent:
    return _evt(
        type_,
        ToolPayload(
            tool_name=name, args={"q": "x"}, result=None,
            latency_ms=0.0, token_cost=None, success=success, error_message=None,
        ),
    )


def _goal(intent: str = "x") -> CognitiveEvent:
    return _evt("goal.created", GoalPayload(intent=intent, priority="high", context=""))


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------


class TestSimilarity:
    def test_identical_events_are_max_similarity(self):
        a = _tool("search")
        b = _tool("search")
        assert event_similarity(a, b) == 1.0

    def test_same_type_different_identity(self):
        a = _tool("search")
        b = _tool("write")
        assert event_similarity(a, b) == 0.7

    def test_same_kind_different_type(self):
        a = _tool("search", type_="tool.called")
        b = _tool("search", type_="tool.returned")
        assert event_similarity(a, b) == 0.3

    def test_completely_different_kinds(self):
        a = _tool("search")
        b = _goal("research")
        # Different payload kinds → mismatch penalty.
        assert event_similarity(a, b) == -0.5


# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------


class TestAlignment:
    def test_empty_vs_empty(self):
        result = align_runs([], [])
        assert result.pairs == []
        assert result.score == 0.0

    def test_empty_vs_non_empty_emits_only_b(self):
        result = align_runs([], [_tool("search")])
        assert len(result.pairs) == 1
        assert result.pairs[0].kind == "only_b"

    def test_identical_runs_match_pair_for_pair(self):
        a = [_tool("a"), _tool("b"), _tool("c")]
        b = [_tool("a"), _tool("b"), _tool("c")]
        result = align_runs(a, b)
        assert all(p.kind == "match" for p in result.pairs)
        assert len(result.pairs) == 3

    def test_extra_event_in_b_is_only_b(self):
        a = [_tool("a"), _tool("b")]
        b = [_tool("a"), _tool("retry"), _tool("b")]
        result = align_runs(a, b)
        kinds = [p.kind for p in result.pairs]
        assert kinds.count("match") == 2
        assert kinds.count("only_b") == 1

    def test_extra_event_in_a_is_only_a(self):
        a = [_tool("a"), _tool("retry"), _tool("b")]
        b = [_tool("a"), _tool("b")]
        result = align_runs(a, b)
        kinds = [p.kind for p in result.pairs]
        assert kinds.count("match") == 2
        assert kinds.count("only_a") == 1

    def test_completely_different_runs_score_negatively(self):
        a = [_tool("a"), _tool("b")]
        b = [_goal("research"), _goal("plan")]
        result = align_runs(a, b)
        # Probably aligns as gap-gap or mismatch — but score should be < 0.
        assert result.score < 0

    def test_alignment_is_deterministic(self):
        a = [_tool("x"), _tool("y")]
        b = [_tool("x"), _tool("z"), _tool("y")]
        r1 = align_runs(a, b)
        r2 = align_runs(a, b)
        assert r1.pairs == r2.pairs
        assert r1.score == r2.score

    def test_config_overrides_apply(self):
        a = [_tool("search")]
        b = [_tool("search")]
        custom = AlignmentConfig(same_type_same_identity=2.5)
        result = align_runs(a, b, config=custom)
        assert result.score == 2.5
