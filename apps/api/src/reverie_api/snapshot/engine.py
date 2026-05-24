"""Snapshot engine — DB-aware front-end for state reconstruction.

Resolves a :class:`RunState` for any event index in any run by:

1. Looking up the nearest **checkpoint** at or before the requested index.
2. Folding events forward from that checkpoint to the target index.

If no checkpoint is available, folds from an empty state. Checkpoints are
created on-demand at multiples of :data:`CHECKPOINT_INTERVAL` so:

- Cold runs incur no extra ingestion cost (Phase 0.2 promised < 5ms).
- Repeated replays are O(checkpoint window) rather than O(events in run).

A simple in-memory LRU caches the most recently produced state per run so
``GET /snapshot?at=N`` followed by ``GET /snapshot?at=N+1`` is incremental.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any

from reverie_schema import CognitiveEvent

from reverie_api.db import Database, RunNotFoundError
from reverie_api.snapshot.fold import fold_event
from reverie_api.snapshot.state import (
    CHECKPOINT_INTERVAL,
    RunState,
    empty_state,
)


class SnapshotNotFoundError(Exception):
    """Raised when a requested snapshot position is out of range."""

    def __init__(self, run_id: str, requested: int, available: int) -> None:
        super().__init__(
            f"snapshot at={requested} is out of range for run {run_id} "
            f"(available: 0..{available})"
        )
        self.run_id = run_id
        self.requested = requested
        self.available = available


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SnapshotEngine:
    """Reconstructs cognitive state at any event index for any run.

    Threading model: methods are async and serialize through the database's
    own write lock when checkpointing. Reads run concurrently with ingest
    (WAL mode lets readers see committed rows without blocking).
    """

    def __init__(self, db: Database, *, lru_size: int = 64) -> None:
        self._db = db
        # (run_id, event_count) -> RunState
        self._lru: OrderedDict[tuple[str, int], RunState] = OrderedDict()
        self._lru_size = lru_size

    # ------------------------------------------------------------------ public

    async def state_at(self, run_id: str, *, at: int) -> RunState:
        """Return the run state after exactly ``at`` events have been folded.

        ``at=0`` returns the empty state. ``at=run.totalEvents`` returns the
        terminal state. Out-of-range values raise :class:`SnapshotNotFoundError`.
        """

        run = await self._db.get_run(run_id)
        if run is None:
            raise RunNotFoundError(run_id)

        total = await self._db.count_events_for_run(run_id)
        if at < 0 or at > total:
            raise SnapshotNotFoundError(run_id, at, total)

        if at == 0:
            return empty_state(run_id)

        cached = self._lru_get(run_id, at)
        if cached is not None:
            return cached

        # Find the nearest checkpoint at or before ``at``.
        cp_count, cp_state = await self._load_nearest_checkpoint(run_id, at)
        state = cp_state if cp_state is not None else empty_state(run_id)

        # Fold remaining events forward.
        if at > cp_count:
            offset = cp_count
            limit = at - cp_count
            events = await self._db.list_events_for_run(
                run_id, limit=limit, offset=offset
            )
            for evt in events:
                state = fold_event(state, evt)

        # If we crossed any checkpoint boundaries, persist them.
        await self._maybe_persist_checkpoints(run_id, state, baseline=cp_count)

        self._lru_put(run_id, at, state)
        return state

    async def terminal_state(self, run_id: str) -> RunState:
        """Convenience: state after all events folded."""

        run = await self._db.get_run(run_id)
        if run is None:
            raise RunNotFoundError(run_id)
        total = await self._db.count_events_for_run(run_id)
        return await self.state_at(run_id, at=total)

    async def first_failure_index(self, run_id: str) -> int | None:
        """Return the 1-based event index that introduced the first failure,
        or ``None`` if the run has no failures.

        Implementation: scans events in timestamp order looking at type. We
        cannot simply use the run-row aggregates because they don't store the
        index of the first failure.
        """

        run = await self._db.get_run(run_id)
        if run is None:
            raise RunNotFoundError(run_id)

        events = await self._db.list_events_for_run(run_id)
        for i, evt in enumerate(events, start=1):
            if evt.type in {
                "goal.failed",
                "tool.failed",
                "validation.failed",
                "retry.exhausted",
            }:
                return i
        return None

    # ------------------------------------------------------------- checkpoints

    async def _load_nearest_checkpoint(
        self, run_id: str, at: int
    ) -> tuple[int, RunState | None]:
        """Return (event_count, state) of the latest checkpoint ≤ ``at``.

        ``(0, None)`` means no checkpoint exists yet.
        """

        cursor = await self._db.conn.execute(
            "SELECT event_count, state_json FROM run_checkpoints "
            "WHERE run_id = ? AND event_count <= ? "
            "ORDER BY event_count DESC LIMIT 1",
            (run_id, at),
        )
        row = await cursor.fetchone()
        if row is None:
            return 0, None
        try:
            state = RunState.model_validate(json.loads(row["state_json"]))
        except Exception:
            # Corrupt or stale schema — treat as missing and rebuild.
            return 0, None
        return int(row["event_count"]), state

    async def _maybe_persist_checkpoints(
        self,
        run_id: str,
        state: RunState,
        *,
        baseline: int,
    ) -> None:
        """If the new state crossed any checkpoint multiples, store them.

        We only store the *latest* checkpoint we crossed. The reducer is
        deterministic so older checkpoints between ``baseline`` and ``state``
        are reproducible from the same data, but storing only one keeps the
        DB lean. Future replays at intermediate positions still hit this one.
        """

        if state.event_count <= baseline:
            return

        # Largest multiple of CHECKPOINT_INTERVAL that's ≤ state.event_count
        # AND > baseline.
        latest = (state.event_count // CHECKPOINT_INTERVAL) * CHECKPOINT_INTERVAL
        if latest <= baseline:
            return

        # We have only the *current* state which is at state.event_count, not
        # necessarily a multiple of the interval. We'll store the checkpoint
        # at state.event_count itself — the lookup query orders by event_count
        # so this works whether or not it's exactly on the boundary.
        # Picking ``latest`` would require re-folding to that exact point.
        await self._save_checkpoint(run_id, state)

    async def _save_checkpoint(self, run_id: str, state: RunState) -> None:
        body = state.model_dump_json(by_alias=False)
        async with self._db._txn():  # noqa: SLF001 — reusing the DB write lock
            await self._db.conn.execute(
                """
                INSERT INTO run_checkpoints (run_id, event_count, state_json, created_at)
                VALUES (?, ?, ?, CAST(strftime('%s', 'now') AS INTEGER) * 1000)
                ON CONFLICT(run_id, event_count) DO UPDATE
                  SET state_json = excluded.state_json,
                      created_at = excluded.created_at
                """,
                (run_id, state.event_count, body),
            )

    async def invalidate_run(self, run_id: str) -> None:
        """Drop all cached state and persisted checkpoints for a run.

        Called when a run is deleted, or to force a full rebuild on the next
        replay (e.g. after a schema migration).
        """

        async with self._db._txn():  # noqa: SLF001
            await self._db.conn.execute(
                "DELETE FROM run_checkpoints WHERE run_id = ?", (run_id,)
            )
        # Drop LRU entries for this run.
        keys_to_drop = [k for k in self._lru if k[0] == run_id]
        for k in keys_to_drop:
            self._lru.pop(k, None)

    # ------------------------------------------------------------------- LRU

    def _lru_get(self, run_id: str, at: int) -> RunState | None:
        key = (run_id, at)
        if key in self._lru:
            self._lru.move_to_end(key)
            return self._lru[key]
        return None

    def _lru_put(self, run_id: str, at: int, state: RunState) -> None:
        key = (run_id, at)
        self._lru[key] = state
        self._lru.move_to_end(key)
        while len(self._lru) > self._lru_size:
            self._lru.popitem(last=False)


# ---------------------------------------------------------------------------
# DI helpers (mirror db.connection)
# ---------------------------------------------------------------------------

_engine_instance: SnapshotEngine | None = None


def set_snapshot_engine(engine: SnapshotEngine | None) -> None:
    global _engine_instance
    _engine_instance = engine


def get_snapshot_engine() -> SnapshotEngine:
    if _engine_instance is None:
        raise RuntimeError("SnapshotEngine has not been initialised")
    return _engine_instance


# Re-export for star-imports from package init.
__all__ = [
    "SnapshotEngine",
    "SnapshotNotFoundError",
    "get_snapshot_engine",
    "set_snapshot_engine",
]


# ---------------------------------------------------------------------------
# Convenience wrapper for retrieving raw events as Pydantic objects.
# ---------------------------------------------------------------------------


def _row_to_event_dict(row: Any) -> dict:
    """Mirrors the conversion in db.connection but returns a plain dict.

    Kept for tests that want to construct events without a real DB.
    """

    return {
        "id": row["id"],
        "type": row["type"],
        "runId": row["run_id"],
        "sessionId": row["session_id"],
        "agentId": row["agent_id"],
        "parentId": row["parent_id"],
        "depth": row["depth"],
        "timestamp": row["timestamp"],
        "durationMs": row["duration_ms"],
        "payload": json.loads(row["payload"]),
        "salience": row["salience"],
        "anomaly": bool(row["anomaly"]),
        "schemaVersion": row["schema_version"],
    }
