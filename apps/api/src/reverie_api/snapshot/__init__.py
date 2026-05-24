"""Snapshot engine — reconstruct cognitive state at any point in a run.

Public surface:

- :class:`RunState` — the state model. Wire-compatible (camelCase JSON).
- :func:`empty_state` — neutral starting state.
- :func:`fold_event` — pure reducer; ``new_state = fold_event(old_state, evt)``.
- :class:`SnapshotEngine` — DB-aware front-end with checkpoint caching.
"""

from reverie_api.snapshot.engine import (
    SnapshotEngine,
    SnapshotNotFoundError,
)
from reverie_api.snapshot.fold import fold_event, fold_events
from reverie_api.snapshot.state import (
    ActiveGoal,
    ActiveTool,
    CHECKPOINT_INTERVAL,
    RecentToolResult,
    RunState,
    empty_state,
)

__all__ = [
    "ActiveGoal",
    "ActiveTool",
    "CHECKPOINT_INTERVAL",
    "RecentToolResult",
    "RunState",
    "SnapshotEngine",
    "SnapshotNotFoundError",
    "empty_state",
    "fold_event",
    "fold_events",
]
