"""Replay-related read endpoints.

Endpoints
---------

``GET /api/v1/runs/{run_id}/snapshot?at=N``
    Reconstruct the cognitive state after exactly ``N`` events have been
    folded. ``N`` defaults to the run's ``totalEvents`` (terminal state).

``GET /api/v1/runs/{run_id}/timeline``
    Compact event timeline — one row per event, ordered by ``timestamp``
    then ``ingest_seq``. Smaller payload than ``/events`` for replay UIs.

``GET /api/v1/runs/{run_id}/failures``
    Returns the index and full event of the first failure observed in the
    run, or 404 if the run had no failures.

These are read-only — replay never mutates state. State sessions /
WebSocket scrubbing are deferred to a later phase.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from reverie_schema import CognitiveEvent

from reverie_api.db import Database, get_database
from reverie_api.db.errors import RunNotFoundError
from reverie_api.snapshot import RunState, SnapshotEngine, SnapshotNotFoundError
from reverie_api.snapshot.engine import get_snapshot_engine

router = APIRouter(prefix="/api/v1", tags=["replay"])


# ---------------------------------------------------------------------------
# /snapshot
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{run_id}/snapshot",
    response_model=RunState,
    response_model_by_alias=True,
    summary="Cognitive state at a given event index",
)
async def get_snapshot(
    run_id: str,
    db: Database = Depends(get_database),
    engine: SnapshotEngine = Depends(get_snapshot_engine),
    at: int | None = Query(
        default=None,
        ge=0,
        description="Event index (0..totalEvents). Defaults to terminal state.",
    ),
) -> RunState:
    if at is None:
        return await engine.terminal_state(run_id)
    return await engine.state_at(run_id, at=at)


# ---------------------------------------------------------------------------
# /timeline
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{run_id}/timeline",
    response_model=list[dict[str, Any]],
    summary="Compact event timeline",
)
async def get_timeline(
    run_id: str,
    db: Database = Depends(get_database),
    limit: int | None = Query(default=None, ge=1, le=10_000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Returns a compact timeline — only the columns useful for replay UIs.

    Equivalent to ``/runs/{id}/events`` but with payload omitted, which makes
    long-run timelines an order of magnitude cheaper to fetch.
    """

    # Verify the run exists so callers see 404 rather than an empty array.
    run = await db.get_run(run_id)
    if run is None:
        raise RunNotFoundError(run_id)

    sql = (
        "SELECT id, type, parent_id, depth, timestamp, duration_ms, anomaly "
        "FROM events WHERE run_id = ? "
        "ORDER BY timestamp ASC, ingest_seq ASC"
    )
    params: list = [run_id]
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

    cursor = await db.conn.execute(sql, params)
    rows = await cursor.fetchall()
    return [
        {
            "id": r["id"],
            "type": r["type"],
            "parentId": r["parent_id"],
            "depth": r["depth"],
            "timestamp": r["timestamp"],
            "durationMs": r["duration_ms"],
            "anomaly": bool(r["anomaly"]),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# /failures
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{run_id}/failures",
    summary="First failure event in the run, if any",
)
async def get_first_failure(
    run_id: str,
    db: Database = Depends(get_database),
    engine: SnapshotEngine = Depends(get_snapshot_engine),
) -> dict[str, Any]:
    """Returns the event index and full event for the first failure.

    Body shape:
        {
          "index": 7,                            # 1-based, matches /timeline order
          "event": { ...full CognitiveEvent... },
          "stateBefore": { ...RunState at index-1... },
        }

    On a clean run, returns 404 with ``error: "no_failures"``.
    """

    idx = await engine.first_failure_index(run_id)
    if idx is None:
        # Use SnapshotNotFoundError-shaped 404 so the route handler in
        # errors.py can translate it. We piggy-back on the existing handler
        # by raising a domain-shaped error.
        raise NoFailuresError(run_id)

    events = await db.list_events_for_run(run_id)
    failure_event: CognitiveEvent = events[idx - 1]

    state_before = await engine.state_at(run_id, at=idx - 1)
    return {
        "index": idx,
        "event": failure_event.model_dump(by_alias=True),
        "stateBefore": state_before.model_dump(by_alias=True),
    }


class NoFailuresError(Exception):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"run has no failures: {run_id}")
        self.run_id = run_id
