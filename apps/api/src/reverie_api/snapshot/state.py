"""``RunState`` — the cognitive state at a moment in time.

Design rules
------------

1. **Bounded.** State is O(active goals + active tools + small recent window),
   not O(events). Replaying a 100k-event run still produces a tiny state
   object.
2. **Wire-friendly.** Pydantic v2 with ``alias_generator=to_camel`` so JSON
   serialization matches the rest of the API (camelCase, ``_type``-less).
3. **Pure.** This module defines data shapes. Folding logic lives in
   ``fold.py``; engine I/O lives in ``engine.py``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

#: Full-snapshot interval. Set conservatively; deltas land in a later phase.
#: Picked from SRS spec (50 events between checkpoints).
CHECKPOINT_INTERVAL = 50

#: Cap on retained "recent" lists so a long run can't blow up state size.
RECENT_TOOL_RESULTS_CAP = 16


class _Base(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
        validate_assignment=True,
    )


class ActiveGoal(_Base):
    """A goal that is currently in progress (created but not yet completed)."""

    event_id: str
    intent: str
    priority: Literal["critical", "high", "medium", "low"]
    parent_id: str | None
    depth: int
    started_at: int  # unix ms


class ActiveTool(_Base):
    """A tool call that has been initiated but not yet returned/failed."""

    event_id: str
    tool_name: str
    parent_id: str | None
    depth: int
    started_at: int
    args_summary: str  # compact stringified args; capped


class RecentToolResult(_Base):
    """A bounded ring of completed tool calls — most recent first."""

    event_id: str
    tool_name: str
    success: bool
    latency_ms: float
    error_message: str | None
    finished_at: int


class FailureSummary(_Base):
    """Pointer to the first failure observed in the run, if any."""

    event_id: str
    type: str  # the failure event's CognitiveEventType
    message: str
    occurred_at: int


class RunState(_Base):
    """Cognitive state at the moment after a particular event.

    Construct a fresh state with :func:`empty_state`. Advance with
    :func:`fold_event`. The :class:`SnapshotEngine` does both for you.
    """

    # Identity
    run_id: str
    # Position — number of events folded into this state, NOT a Reverie event id.
    event_count: int = 0
    last_event_id: str | None = None
    last_timestamp: int = 0  # unix ms; 0 means "no events yet"

    # Topology — currently active goals and tool calls.
    active_goals: list[ActiveGoal] = Field(default_factory=list)
    active_tools: list[ActiveTool] = Field(default_factory=list)

    # Bounded windows — recent activity that's useful to a debugger.
    recent_tool_results: list[RecentToolResult] = Field(default_factory=list)

    # Cumulative metrics — match the run-row aggregates so they cross-check.
    total_tokens: int = 0
    total_tool_calls: int = 0
    total_retries: int = 0
    total_subagents: int = 0
    total_failures: int = 0

    # Goal-level outcomes seen so far.
    completed_goals: list[str] = Field(default_factory=list)  # event ids
    failed_goals: list[str] = Field(default_factory=list)

    # First observed failure — useful for ``--jump-failure``.
    first_failure: FailureSummary | None = None

    # Latest reasoning extracted (if the lab exposes any).
    last_reasoning_summary: str | None = None
    last_reasoning_model: str | None = None

    # Context-window pressure (most recent context.truncated event).
    context_tokens_used: int = 0
    context_token_limit: int = 0
    context_percent_used: float = 0.0


def empty_state(run_id: str) -> RunState:
    """Return a fresh, neutral state for a run."""

    return RunState(run_id=run_id)
