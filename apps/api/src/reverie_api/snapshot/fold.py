"""Pure reducer: ``new_state = fold_event(old_state, evt)``.

Treats the event log as the source of truth and computes :class:`RunState`
deterministically. Two invariants hold for any event sequence:

* ``fold_events([e1, e2, ...])`` is equivalent to repeatedly calling
  ``fold_event``; the function is associative and order-preserving.
* ``state.event_count == len(events)`` — never deviates.

Folding never raises on schema-valid input. Unknown event types are tolerated
(they just bump ``event_count``); any future event type is forward-compatible
out of the box.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from reverie_schema import CognitiveEvent

from reverie_api.snapshot.state import (
    RECENT_TOOL_RESULTS_CAP,
    ActiveGoal,
    ActiveTool,
    FailureSummary,
    RecentToolResult,
    RunState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _summarise_args(args: Any, *, cap: int = 200) -> str:
    """Compact, readable representation of tool args. Never raises."""

    try:
        s = json.dumps(args, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        s = repr(args)
    return s if len(s) <= cap else s[: cap - 1] + "…"


def _push_recent(
    bucket: list[RecentToolResult], item: RecentToolResult, cap: int
) -> list[RecentToolResult]:
    """Return a new list with ``item`` prepended and tail trimmed to ``cap``."""

    return [item, *bucket[: cap - 1]]


def _drop_active_tool(
    actives: list[ActiveTool],
    event_id: str,
    span_link: str | None,
    *,
    parent_id: str | None,
    depth: int,
) -> tuple[list[ActiveTool], ActiveTool | None]:
    """Remove the ``ActiveTool`` matching this completion event.

    Matches in priority order:
      1. ``g.event_id == span_link`` — explicit parent-link convention
         (end.parent_id = start.id).
      2. ``g.event_id == event_id`` — same id used for start and end.
      3. **Sibling-by-position**: the most recently started active tool that
         shares the same ``parent_id`` and ``depth`` as the end event. The
         OpenAI adapter uses this convention (start/end are siblings under
         the same parent).
    """

    # 1) Explicit parent-link.
    if span_link is not None:
        for i, t in enumerate(actives):
            if t.event_id == span_link:
                return actives[:i] + actives[i + 1 :], t
    # 2) Same-id (rare).
    for i, t in enumerate(actives):
        if t.event_id == event_id:
            return actives[:i] + actives[i + 1 :], t
    # 3) Sibling-by-position. Iterate in reverse so we pick the most recently
    # started match — closest to LIFO span semantics.
    for i in range(len(actives) - 1, -1, -1):
        t = actives[i]
        if t.parent_id == parent_id and t.depth == depth:
            return actives[:i] + actives[i + 1 :], t
    return actives, None


def _drop_active_goal(
    actives: list[ActiveGoal],
    event_id: str,
    span_link: str | None,
    *,
    parent_id: str | None,
    depth: int,
) -> tuple[list[ActiveGoal], ActiveGoal | None]:
    if span_link is not None:
        for i, g in enumerate(actives):
            if g.event_id == span_link:
                return actives[:i] + actives[i + 1 :], g
    for i, g in enumerate(actives):
        if g.event_id == event_id:
            return actives[:i] + actives[i + 1 :], g
    for i in range(len(actives) - 1, -1, -1):
        g = actives[i]
        if g.parent_id == parent_id and g.depth == depth:
            return actives[:i] + actives[i + 1 :], g
    return actives, None


def _failure_message(payload: Any) -> str:
    """Best-effort extraction of a human-readable failure message."""

    kind = getattr(payload, "kind", None)
    if kind == "tool":
        return getattr(payload, "error_message", None) or "tool failed"
    if kind == "goal":
        ctx = getattr(payload, "context", "") or ""
        return f"goal failed: {ctx[:200]}" if ctx else "goal failed"
    if kind == "validation":
        details = getattr(payload, "details", "") or ""
        return f"validation failed: {details[:200]}" if details else "validation failed"
    if kind == "retry":
        return getattr(payload, "previous_error", None) or "retry exhausted"
    return "failure"


# ---------------------------------------------------------------------------
# Public reducer
# ---------------------------------------------------------------------------


def fold_event(state: RunState, event: CognitiveEvent) -> RunState:
    """Return a new :class:`RunState` with ``event`` applied.

    ``state`` is treated as immutable — the returned object is a fresh
    Pydantic model. Callers can safely cache earlier states.
    """

    # Build the next state from a copy of the current one.
    data = state.model_dump(by_alias=False)

    # Bump position counters.
    data["event_count"] = state.event_count + 1
    data["last_event_id"] = event.id
    data["last_timestamp"] = event.timestamp

    payload = event.payload
    kind = getattr(payload, "kind", None)
    type_ = event.type

    # ---------------------------------------------------------------- goals
    if type_ == "goal.created":
        data["active_goals"] = [
            *state.active_goals,
            ActiveGoal(
                event_id=event.id,
                intent=getattr(payload, "intent", "") or "",
                priority=getattr(payload, "priority", "medium"),
                parent_id=event.parent_id,
                depth=event.depth,
                started_at=event.timestamp,
            ).model_dump(by_alias=False),
        ]
    elif type_ in {"goal.completed", "goal.failed"}:
        new_actives, matched = _drop_active_goal(
            state.active_goals,
            event.id,
            event.parent_id,
            parent_id=event.parent_id,
            depth=event.depth,
        )
        data["active_goals"] = [g.model_dump(by_alias=False) for g in new_actives]
        # Track the *start* event id (the goal that completed/failed). If we
        # couldn't match a started goal, fall back to the end event's id so
        # consumers still see something — this can happen when an end event
        # arrives without a known start (replay from mid-run, or schema
        # drift).
        goal_event_id = matched.event_id if matched is not None else event.id
        if type_ == "goal.completed":
            data["completed_goals"] = [*state.completed_goals, goal_event_id]
        else:
            data["failed_goals"] = [*state.failed_goals, goal_event_id]
            data["total_failures"] = state.total_failures + 1
            if state.first_failure is None:
                data["first_failure"] = FailureSummary(
                    event_id=event.id,
                    type=type_,
                    message=_failure_message(payload),
                    occurred_at=event.timestamp,
                ).model_dump(by_alias=False)

    # ---------------------------------------------------------------- tools
    elif type_ == "tool.called":
        data["total_tool_calls"] = state.total_tool_calls + 1
        data["active_tools"] = [
            *state.active_tools,
            ActiveTool(
                event_id=event.id,
                tool_name=getattr(payload, "tool_name", "unknown"),
                parent_id=event.parent_id,
                depth=event.depth,
                started_at=event.timestamp,
                args_summary=_summarise_args(getattr(payload, "args", {})),
            ).model_dump(by_alias=False),
        ]
    elif type_ in {"tool.returned", "tool.failed"}:
        new_actives, _matched = _drop_active_tool(
            state.active_tools,
            event.id,
            event.parent_id,
            parent_id=event.parent_id,
            depth=event.depth,
        )
        data["active_tools"] = [t.model_dump(by_alias=False) for t in new_actives]

        if kind == "tool":
            tc = getattr(payload, "token_cost", None)
            if isinstance(tc, int):
                data["total_tokens"] = state.total_tokens + tc

            success = bool(getattr(payload, "success", type_ == "tool.returned"))
            err = getattr(payload, "error_message", None)
            recent = RecentToolResult(
                event_id=event.id,
                tool_name=getattr(payload, "tool_name", "unknown"),
                success=success,
                latency_ms=float(getattr(payload, "latency_ms", 0.0) or 0.0),
                error_message=err,
                finished_at=event.timestamp,
            )
            data["recent_tool_results"] = [
                r.model_dump(by_alias=False)
                for r in _push_recent(
                    state.recent_tool_results, recent, RECENT_TOOL_RESULTS_CAP
                )
            ]

        if type_ == "tool.failed":
            data["total_failures"] = state.total_failures + 1
            if state.first_failure is None:
                data["first_failure"] = FailureSummary(
                    event_id=event.id,
                    type=type_,
                    message=_failure_message(payload),
                    occurred_at=event.timestamp,
                ).model_dump(by_alias=False)

    # ------------------------------------------------------------- retries
    elif type_ == "retry.triggered":
        data["total_retries"] = state.total_retries + 1
    elif type_ == "retry.exhausted":
        data["total_retries"] = state.total_retries + 1
        data["total_failures"] = state.total_failures + 1
        if state.first_failure is None:
            data["first_failure"] = FailureSummary(
                event_id=event.id,
                type=type_,
                message=_failure_message(payload),
                occurred_at=event.timestamp,
            ).model_dump(by_alias=False)

    # ------------------------------------------------------------ subagents
    elif type_ == "subagent.spawned":
        data["total_subagents"] = state.total_subagents + 1
    elif type_ == "subagent.completed":
        # No state change beyond position counters; subagent runs are tracked
        # as their own runs in the broader Reverie data model.
        pass

    # ----------------------------------------------------------- validations
    elif type_ == "validation.failed":
        data["total_failures"] = state.total_failures + 1
        if state.first_failure is None:
            data["first_failure"] = FailureSummary(
                event_id=event.id,
                type=type_,
                message=_failure_message(payload),
                occurred_at=event.timestamp,
            ).model_dump(by_alias=False)

    # ------------------------------------------------------------- reasoning
    elif type_ == "reasoning.extracted" and kind == "reasoning":
        summary = getattr(payload, "summary", None)
        model_id = getattr(payload, "model_id", None)
        tokens = getattr(payload, "tokens_used", None)
        if summary is not None:
            data["last_reasoning_summary"] = summary
        if model_id is not None:
            data["last_reasoning_model"] = model_id
        if isinstance(tokens, int):
            data["total_tokens"] = state.total_tokens + tokens

    # --------------------------------------------------------------- context
    elif type_ == "context.truncated" and kind == "context":
        data["context_tokens_used"] = int(getattr(payload, "tokens_used", 0))
        data["context_token_limit"] = int(getattr(payload, "token_limit", 0))
        data["context_percent_used"] = float(getattr(payload, "percent_used", 0.0))

    # Unknown event types: position counters already advanced; no field
    # changes. This is forward-compatible with future event types.

    return RunState(**data)


def fold_events(events: Iterable[CognitiveEvent], *, run_id: str) -> RunState:
    """Convenience: fold an iterable of events from an empty state."""

    from reverie_api.snapshot.state import empty_state

    state = empty_state(run_id)
    for evt in events:
        state = fold_event(state, evt)
    return state
