"""Tests for the pure ``fold_event`` reducer.

These exercise every CognitiveEventType branch independently, plus
order-invariance on a multi-event sequence. No I/O, no DB.
"""

from __future__ import annotations

import uuid

import pytest
from reverie_schema import (
    CognitiveEvent,
    ContextPayload,
    GoalPayload,
    ReasoningPayload,
    RetryPayload,
    SubagentPayload,
    ToolPayload,
    ValidationPayload,
)

from reverie_api.snapshot import (
    CHECKPOINT_INTERVAL,
    RunState,
    empty_state,
    fold_event,
    fold_events,
)


RUN_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"


def _new_id() -> str:
    return str(uuid.uuid4())


def _evt(
    type_: str,
    payload,
    *,
    event_id: str | None = None,
    parent_id: str | None = None,
    timestamp: int = 1_700_000_000_000,
    depth: int = 0,
) -> CognitiveEvent:
    return CognitiveEvent(
        id=event_id or _new_id(),
        type=type_,
        run_id=RUN_ID,
        session_id=SESSION_ID,
        agent_id="agent-test",
        parent_id=parent_id,
        depth=depth,
        timestamp=timestamp,
        duration_ms=None,
        payload=payload,
    )


# ---------------------------------------------------------------------------
# Identity / counters
# ---------------------------------------------------------------------------


class TestPositionCounters:
    def test_empty_state_counts_zero(self):
        s = empty_state(RUN_ID)
        assert s.event_count == 0
        assert s.last_event_id is None
        assert s.last_timestamp == 0

    def test_counters_increment_on_unknown_event(self):
        # Even unknown event types must bump position so the counter never
        # stalls under future schema additions.
        s = empty_state(RUN_ID)
        evt = _evt(
            "context.truncated",
            ContextPayload(tokens_used=1, token_limit=100, percent_used=1.0, truncated_messages=0),
        )
        s2 = fold_event(s, evt)
        assert s2.event_count == 1
        assert s2.last_event_id == evt.id
        assert s2.last_timestamp == evt.timestamp

    def test_fold_events_matches_iterative_fold(self):
        events = [
            _evt("goal.created", GoalPayload(intent="x", priority="high", context="")),
            _evt("tool.called", _tool_payload("a")),
            _evt("tool.returned", _tool_payload("a", success=True), parent_id=None),
        ]
        a = fold_events(events, run_id=RUN_ID)
        b = empty_state(RUN_ID)
        for e in events:
            b = fold_event(b, e)
        assert a == b


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------


class TestGoals:
    def test_goal_created_pushes_active(self):
        evt = _evt("goal.created", GoalPayload(intent="research", priority="high", context=""))
        s = fold_event(empty_state(RUN_ID), evt)
        assert len(s.active_goals) == 1
        g = s.active_goals[0]
        assert g.intent == "research"
        assert g.priority == "high"
        assert g.event_id == evt.id

    def test_goal_completed_drops_active_and_marks_completed(self):
        start = _evt("goal.created", GoalPayload(intent="r", priority="high", context=""))
        end = _evt(
            "goal.completed",
            GoalPayload(intent="r", priority="high", context=""),
            parent_id=start.id,  # link end → start (same parent or referencing start)
        )
        # Use parent linkage so the matcher finds the start event.
        end_linked = _evt(
            "goal.completed",
            GoalPayload(intent="r", priority="high", context=""),
            parent_id=None,
        )
        # Force the link by setting parent_id == start.id on a fresh event.
        end_with_link = end_linked.model_copy(update={"parent_id": start.id})

        s = fold_event(empty_state(RUN_ID), start)
        s = fold_event(s, end_with_link)

        assert s.active_goals == []
        assert start.id in s.completed_goals
        assert s.failed_goals == []

    def test_goal_failed_records_first_failure(self):
        start = _evt("goal.created", GoalPayload(intent="r", priority="high", context=""))
        fail = _evt(
            "goal.failed",
            GoalPayload(intent="r", priority="high", context="boom"),
            parent_id=start.id,
        )
        s = fold_event(empty_state(RUN_ID), start)
        s = fold_event(s, fail)

        assert s.first_failure is not None
        assert s.first_failure.type == "goal.failed"
        assert "boom" in s.first_failure.message
        assert s.total_failures == 1


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def _tool_payload(name: str, *, success: bool = True, token_cost: int | None = None, error: str | None = None) -> ToolPayload:
    return ToolPayload(
        tool_name=name,
        args={"q": "x"},
        result={"ok": True} if success else None,
        latency_ms=12.5,
        token_cost=token_cost,
        success=success,
        error_message=error,
    )


class TestTools:
    def test_tool_called_pushes_active_and_bumps_counter(self):
        s = fold_event(empty_state(RUN_ID), _evt("tool.called", _tool_payload("search")))
        assert s.total_tool_calls == 1
        assert len(s.active_tools) == 1
        assert s.active_tools[0].tool_name == "search"

    def test_tool_returned_drops_active_and_records_recent(self):
        start = _evt("tool.called", _tool_payload("search"))
        end = _evt(
            "tool.returned",
            _tool_payload("search", token_cost=42),
            parent_id=start.id,
        )
        s = fold_event(empty_state(RUN_ID), start)
        s = fold_event(s, end)

        assert s.active_tools == []
        assert s.total_tool_calls == 1  # not double-counted on return
        assert s.total_tokens == 42
        assert len(s.recent_tool_results) == 1
        recent = s.recent_tool_results[0]
        assert recent.tool_name == "search"
        assert recent.success is True

    def test_tool_failed_records_first_failure(self):
        start = _evt("tool.called", _tool_payload("bad"))
        end = _evt(
            "tool.failed",
            _tool_payload("bad", success=False, error="timeout"),
            parent_id=start.id,
        )
        s = fold_event(empty_state(RUN_ID), start)
        s = fold_event(s, end)

        assert s.first_failure is not None
        assert s.first_failure.type == "tool.failed"
        assert "timeout" in s.first_failure.message
        assert s.total_failures == 1
        assert s.recent_tool_results[0].success is False

    def test_first_failure_only_records_once(self):
        start1 = _evt("tool.called", _tool_payload("a"))
        fail1 = _evt(
            "tool.failed",
            _tool_payload("a", success=False, error="first"),
            parent_id=start1.id,
            timestamp=2,
        )
        start2 = _evt("tool.called", _tool_payload("b"), timestamp=3)
        fail2 = _evt(
            "tool.failed",
            _tool_payload("b", success=False, error="second"),
            parent_id=start2.id,
            timestamp=4,
        )
        s = empty_state(RUN_ID)
        for e in (start1, fail1, start2, fail2):
            s = fold_event(s, e)

        assert s.first_failure is not None
        assert "first" in s.first_failure.message
        assert s.total_failures == 2

    def test_recent_tool_results_is_capped(self):
        s = empty_state(RUN_ID)
        # Generate 30 completed tool calls; only the latest cap should survive.
        for i in range(30):
            start = _evt("tool.called", _tool_payload(f"t{i}"))
            end = _evt(
                "tool.returned",
                _tool_payload(f"t{i}", token_cost=1),
                parent_id=start.id,
            )
            s = fold_event(s, start)
            s = fold_event(s, end)

        from reverie_api.snapshot.state import RECENT_TOOL_RESULTS_CAP

        assert len(s.recent_tool_results) == RECENT_TOOL_RESULTS_CAP
        # Most recent first.
        assert s.recent_tool_results[0].tool_name == "t29"
        assert s.recent_tool_results[-1].tool_name == f"t{30 - RECENT_TOOL_RESULTS_CAP}"

    def test_sibling_convention_matches_by_parent_and_depth(self):
        """The OpenAI adapter emits start and end as **siblings** under the
        same parent. The matcher must find the right active tool by
        parent + depth + LIFO ordering, even when end.parent_id != start.id.
        """

        common_parent = _new_id()
        start = _evt(
            "tool.called", _tool_payload("search"),
            parent_id=common_parent, depth=1,
        )
        end = _evt(
            "tool.returned", _tool_payload("search", token_cost=10),
            parent_id=common_parent, depth=1,
            timestamp=2,
        )
        s = fold_event(empty_state(RUN_ID), start)
        s = fold_event(s, end)

        assert s.active_tools == []
        assert s.recent_tool_results[0].tool_name == "search"
        assert s.total_tokens == 10

    def test_sibling_convention_picks_lifo_when_multiple_active(self):
        """When two tools at the same depth/parent are concurrently active,
        the next end event matches the most-recently-started one (LIFO) —
        the only deterministic, span-stack-faithful choice.
        """

        common_parent = _new_id()
        start_a = _evt(
            "tool.called", _tool_payload("a"),
            parent_id=common_parent, depth=1, timestamp=1,
        )
        start_b = _evt(
            "tool.called", _tool_payload("b"),
            parent_id=common_parent, depth=1, timestamp=2,
        )
        end_b = _evt(
            "tool.returned", _tool_payload("b"),
            parent_id=common_parent, depth=1, timestamp=3,
        )
        s = empty_state(RUN_ID)
        for e in (start_a, start_b, end_b):
            s = fold_event(s, e)

        # `a` should still be active; `b` should have been dropped.
        assert len(s.active_tools) == 1
        assert s.active_tools[0].tool_name == "a"
        assert s.recent_tool_results[0].tool_name == "b"


# ---------------------------------------------------------------------------
# Retries / Subagents / Validation / Reasoning / Context
# ---------------------------------------------------------------------------


class TestOtherEventTypes:
    def test_retry_triggered_increments_counter(self):
        evt = _evt(
            "retry.triggered",
            RetryPayload(reason="timeout", attempt=2, max_attempts=3, previous_error="x", backoff_ms=100),
        )
        s = fold_event(empty_state(RUN_ID), evt)
        assert s.total_retries == 1
        assert s.total_failures == 0  # retry triggered != failure

    def test_retry_exhausted_marks_failure(self):
        evt = _evt(
            "retry.exhausted",
            RetryPayload(reason="timeout", attempt=3, max_attempts=3, previous_error="x", backoff_ms=0),
        )
        s = fold_event(empty_state(RUN_ID), evt)
        assert s.total_retries == 1
        assert s.total_failures == 1
        assert s.first_failure is not None
        assert s.first_failure.type == "retry.exhausted"

    def test_subagent_spawned(self):
        evt = _evt(
            "subagent.spawned",
            SubagentPayload(agent_type="researcher", task="t", delegated_goal_id=None, child_run_id=None),
        )
        s = fold_event(empty_state(RUN_ID), evt)
        assert s.total_subagents == 1

    def test_validation_failed_recorded(self):
        evt = _evt(
            "validation.failed",
            ValidationPayload(check_name="pii", passed=False, severity="error", details="forbidden"),
        )
        s = fold_event(empty_state(RUN_ID), evt)
        assert s.total_failures == 1
        assert s.first_failure is not None
        assert "forbidden" in s.first_failure.message

    def test_reasoning_extracted_updates_summary_and_tokens(self):
        evt = _evt(
            "reasoning.extracted",
            ReasoningPayload(raw_text=None, summary="thought it through", model_id="gpt-4o-mini", tokens_used=120),
        )
        s = fold_event(empty_state(RUN_ID), evt)
        assert s.last_reasoning_summary == "thought it through"
        assert s.last_reasoning_model == "gpt-4o-mini"
        assert s.total_tokens == 120

    def test_context_truncated_updates_pressure(self):
        evt = _evt(
            "context.truncated",
            ContextPayload(tokens_used=7500, token_limit=8000, percent_used=93.75, truncated_messages=4),
        )
        s = fold_event(empty_state(RUN_ID), evt)
        assert s.context_tokens_used == 7500
        assert s.context_token_limit == 8000
        assert s.context_percent_used == pytest.approx(93.75)


# ---------------------------------------------------------------------------
# Wire format
# ---------------------------------------------------------------------------


class TestWireFormat:
    def test_state_json_uses_camelcase(self):
        s = empty_state(RUN_ID)
        wire = s.model_dump(by_alias=True)
        assert "runId" in wire
        assert "eventCount" in wire
        assert "activeGoals" in wire
        assert "totalToolCalls" in wire
        assert "lastReasoningSummary" in wire
        # snake-case forms must NOT appear on the wire.
        for forbidden in ("run_id", "event_count", "active_goals", "total_tool_calls"):
            assert forbidden not in wire

    def test_state_round_trips_through_json(self):
        # Build a non-trivial state.
        s = empty_state(RUN_ID)
        s = fold_event(s, _evt("goal.created", GoalPayload(intent="r", priority="high", context="")))
        s = fold_event(s, _evt("tool.called", _tool_payload("x")))

        import json as _json

        blob = s.model_dump_json(by_alias=True)
        restored = RunState.model_validate(_json.loads(blob))
        assert restored == s


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_checkpoint_interval_constant_is_50():
    # Pinned by SRS — changing this is a perf decision, not a casual edit.
    assert CHECKPOINT_INTERVAL == 50
