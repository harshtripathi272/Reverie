"""Async SQLite wrapper with append-only event semantics.

Design notes
------------

- **One connection.** SQLite is single-writer. Holding one connection for the
  whole process and serializing writes via an ``asyncio.Lock`` is simpler than
  a pool and equally fast for our workload (small structured records, no
  contention from concurrent writers).
- **WAL mode.** Readers don't block writers and vice versa. The ``/stream``
  WebSocket can issue catch-up reads while ingest writes flow.
- **Foreign keys ON.** SQLite ships with FKs disabled. We enforce them so the
  ``events.run_id`` reference is real.
- **Atomic batches.** Inserting a batch updates the run aggregate counters in
  the same transaction.
- **No business logic here.** This module exposes primitive operations
  (create_run, insert_events, fetch_*). HTTP-layer concerns live in routes.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from reverie_schema import (
    CognitiveEvent,
    Run,
    RunCreate,
    RunUpdate,
)

from reverie_api.db.errors import (
    BatchValidationError,
    DuplicateEventError,
    DuplicateRunError,
    RunNotFoundError,
    RunPinnedError,
)
from reverie_api.db.migrations import apply_migrations


def _row_to_run(row: aiosqlite.Row) -> Run:
    """Translate a `runs` row into the wire-shaped `Run` model."""

    return Run.model_validate(
        {
            "id": row["id"],
            "sessionId": row["session_id"],
            "agentId": row["agent_id"],
            "runtime": row["runtime"],
            "startedAt": row["started_at"],
            "completedAt": row["completed_at"],
            "status": row["status"],
            "goal": row["goal"],
            "totalEvents": row["total_events"],
            "totalTokens": row["total_tokens"],
            "totalToolCalls": row["total_tool_calls"],
            "totalRetries": row["total_retries"],
            "totalSubagents": row["total_subagents"],
            "pinned": bool(row["pinned"]),
            "tags": json.loads(row["tags"] or "[]"),
            "createdAt": row["created_at"],
        }
    )


def _row_to_event(row: aiosqlite.Row) -> CognitiveEvent:
    """Translate an `events` row into a `CognitiveEvent`.

    The payload column stores the wire-format (camelCase) JSON of the original
    event payload, so re-validation through Pydantic preserves invariants.
    """

    return CognitiveEvent.model_validate(
        {
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
    )


# Map event.type → which run aggregate counter (if any) to bump.
_AGGREGATE_BY_TYPE: dict[str, str] = {
    "tool.called": "total_tool_calls",
    "retry.triggered": "total_retries",
    "subagent.spawned": "total_subagents",
}


def _token_delta(event: CognitiveEvent) -> int:
    """Tokens to add to ``total_tokens`` for this event, if any."""

    payload = event.payload
    # Pydantic discriminated union — branch on .kind.
    kind = getattr(payload, "kind", None)
    if kind == "tool":
        return int(payload.token_cost or 0)
    if kind == "reasoning":
        return int(payload.tokens_used or 0)
    if kind == "context":
        # context events carry a *snapshot* of total used, not a delta.
        return 0
    return 0


class Database:
    """Async wrapper around a single SQLite connection.

    Construct via the :func:`get_database` lifespan helper rather than
    instantiating directly.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._write_lock = asyncio.Lock()
        # Monotonic ingest counter — assigned to events at insert time so we
        # can produce a deterministic order even when timestamps collide.
        self._ingest_seq = 0
        self._seq_lock = asyncio.Lock()

    # ------------------------------------------------------------------ lifecycle

    async def connect(self) -> None:
        if self._conn is not None:
            return

        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = await aiosqlite.connect(self._db_path, isolation_level=None)
        # ``isolation_level=None`` means autocommit; we use explicit BEGIN/COMMIT.
        conn.row_factory = aiosqlite.Row

        # Pragmas — order matters. WAL must come before the first write.
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("PRAGMA journal_mode = WAL")
        await conn.execute("PRAGMA synchronous = NORMAL")
        await conn.execute("PRAGMA temp_store = MEMORY")
        await conn.execute("PRAGMA busy_timeout = 5000")

        self._conn = conn

        await apply_migrations(conn)

        # Initialise the in-memory ingest counter from whatever's on disk.
        cursor = await conn.execute("SELECT COALESCE(MAX(ingest_seq), 0) FROM events")
        row = await cursor.fetchone()
        self._ingest_seq = int(row[0]) if row else 0

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.connect() has not been called")
        return self._conn

    # ------------------------------------------------------------------ tx helper

    @asynccontextmanager
    async def _txn(self):
        """Begin/commit a write transaction under the write lock."""

        async with self._write_lock:
            await self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield
            except Exception:
                await self.conn.rollback()
                raise
            else:
                await self.conn.commit()

    async def _next_seq(self, n: int = 1) -> int:
        """Reserve ``n`` ingest sequence numbers, returning the first."""

        async with self._seq_lock:
            start = self._ingest_seq + 1
            self._ingest_seq += n
            return start

    # ------------------------------------------------------------------ runs

    async def create_run(self, payload: RunCreate) -> Run:
        async with self._txn():
            try:
                await self.conn.execute(
                    """
                    INSERT INTO runs (
                        id, session_id, agent_id, runtime, started_at,
                        completed_at, status, goal,
                        total_events, total_tokens, total_tool_calls,
                        total_retries, total_subagents,
                        pinned, tags, created_at
                    ) VALUES (
                        :id, :session_id, :agent_id, :runtime, :started_at,
                        NULL, 'running', :goal,
                        0, 0, 0, 0, 0,
                        0, '[]', :created_at
                    )
                    """,
                    {
                        "id": payload.run_id,
                        "session_id": payload.session_id,
                        "agent_id": payload.agent_id,
                        "runtime": payload.runtime,
                        "started_at": payload.started_at,
                        "goal": payload.goal,
                        "created_at": payload.started_at,
                    },
                )
            except aiosqlite.IntegrityError as exc:
                raise DuplicateRunError(payload.run_id) from exc

        run = await self.get_run(payload.run_id)
        assert run is not None  # just inserted
        return run

    async def get_run(self, run_id: str) -> Run | None:
        cursor = await self.conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
        row = await cursor.fetchone()
        return _row_to_run(row) if row else None

    async def list_runs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        session_id: str | None = None,
        status: str | None = None,
    ) -> list[Run]:
        clauses: list[str] = []
        params: list = []
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])

        cursor = await self.conn.execute(
            f"SELECT * FROM runs {where} ORDER BY started_at DESC LIMIT ? OFFSET ?",
            params,
        )
        rows = await cursor.fetchall()
        return [_row_to_run(r) for r in rows]

    async def count_runs(
        self,
        *,
        session_id: str | None = None,
        status: str | None = None,
    ) -> int:
        clauses: list[str] = []
        params: list = []
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        cursor = await self.conn.execute(f"SELECT COUNT(*) FROM runs {where}", params)
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def update_run(self, run_id: str, update: RunUpdate) -> Run:
        # `exclude_unset=True` mirrors PATCH semantics — only set what the
        # caller specified.
        fields = update.model_dump(exclude_unset=True, by_alias=False)
        if not fields:
            existing = await self.get_run(run_id)
            if existing is None:
                raise RunNotFoundError(run_id)
            return existing

        column_map = {
            "status": "status",
            "completed_at": "completed_at",
            "goal": "goal",
        }
        sets: list[str] = []
        params: list = []
        for key, value in fields.items():
            col = column_map.get(key)
            if col is None:
                continue  # unknown field — ignore (Pydantic already filtered)
            sets.append(f"{col} = ?")
            params.append(value)
        params.append(run_id)

        async with self._txn():
            cursor = await self.conn.execute(
                f"UPDATE runs SET {', '.join(sets)} WHERE id = ?", params
            )
            if cursor.rowcount == 0:
                raise RunNotFoundError(run_id)

        run = await self.get_run(run_id)
        assert run is not None
        return run

    async def set_pinned(self, run_id: str, pinned: bool) -> Run:
        async with self._txn():
            cursor = await self.conn.execute(
                "UPDATE runs SET pinned = ? WHERE id = ?",
                (1 if pinned else 0, run_id),
            )
            if cursor.rowcount == 0:
                raise RunNotFoundError(run_id)
        run = await self.get_run(run_id)
        assert run is not None
        return run

    async def delete_run(self, run_id: str) -> None:
        async with self._txn():
            cursor = await self.conn.execute(
                "SELECT pinned FROM runs WHERE id = ?", (run_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                raise RunNotFoundError(run_id)
            if int(row["pinned"]):
                raise RunPinnedError(run_id)
            # FK ON DELETE CASCADE removes events.
            await self.conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))

    # ------------------------------------------------------------------ events

    async def insert_events(self, events: list[CognitiveEvent]) -> int:
        """Insert a batch of events atomically. Returns count inserted.

        - All events must reference existing runs. If any do not, raises
          :class:`BatchValidationError` with the full list of missing run IDs
          and inserts nothing.
        - Run aggregate counters are updated in the same transaction.
        - Duplicate event IDs (across the batch or against existing rows) cause
          the whole batch to fail with `aiosqlite.IntegrityError`.
        """

        if not events:
            return 0

        # Pre-flight: every distinct run_id must exist.
        run_ids = {e.run_id for e in events}
        placeholders = ",".join("?" * len(run_ids))
        cursor = await self.conn.execute(
            f"SELECT id FROM runs WHERE id IN ({placeholders})", list(run_ids)
        )
        rows = await cursor.fetchall()
        existing = {r["id"] for r in rows}
        missing = sorted(run_ids - existing)
        if missing:
            raise BatchValidationError(missing)

        # Reserve a contiguous block of ingest sequence numbers so the batch
        # has a deterministic in-batch order even with identical timestamps.
        first_seq = await self._next_seq(len(events))

        rows_to_insert = []
        # Per-run aggregate deltas — accumulated, then applied in one UPDATE.
        run_delta: dict[str, dict[str, int]] = {}
        for i, evt in enumerate(events):
            rows_to_insert.append(
                (
                    evt.id,
                    evt.run_id,
                    evt.type,
                    evt.session_id,
                    evt.agent_id,
                    evt.parent_id,
                    evt.depth,
                    evt.timestamp,
                    evt.duration_ms,
                    # Payload is stored as the wire-format JSON so re-reads can
                    # validate against the same schema.
                    evt.payload.model_dump_json(),
                    evt.salience,
                    1 if evt.anomaly else 0,
                    evt.schema_version,
                    first_seq + i,
                )
            )
            d = run_delta.setdefault(
                evt.run_id,
                {
                    "total_events": 0,
                    "total_tokens": 0,
                    "total_tool_calls": 0,
                    "total_retries": 0,
                    "total_subagents": 0,
                },
            )
            d["total_events"] += 1
            d["total_tokens"] += _token_delta(evt)
            counter = _AGGREGATE_BY_TYPE.get(evt.type)
            if counter is not None:
                d[counter] += 1

        try:
            async with self._txn():
                await self.conn.executemany(
                    """
                    INSERT INTO events (
                        id, run_id, type, session_id, agent_id,
                        parent_id, depth, timestamp, duration_ms,
                        payload, salience, anomaly, schema_version, ingest_seq
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows_to_insert,
                )
                for rid, delta in run_delta.items():
                    await self.conn.execute(
                        """
                        UPDATE runs SET
                            total_events     = total_events     + :total_events,
                            total_tokens     = total_tokens     + :total_tokens,
                            total_tool_calls = total_tool_calls + :total_tool_calls,
                            total_retries    = total_retries    + :total_retries,
                            total_subagents  = total_subagents  + :total_subagents
                        WHERE id = :run_id
                        """,
                        {**delta, "run_id": rid},
                    )
        except aiosqlite.IntegrityError as exc:
            # Most common cause: duplicate event id (PK violation). Either the
            # batch contains repeats among itself, or one collides with the
            # existing log. The transaction is already rolled back.
            msg = str(exc)
            if "events.id" in msg or "UNIQUE constraint" in msg:
                raise DuplicateEventError() from exc
            raise

        return len(events)

    async def insert_event(self, event: CognitiveEvent) -> None:
        await self.insert_events([event])

    async def list_events_for_run(
        self,
        run_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CognitiveEvent]:
        # Confirm the run exists so callers can distinguish "no events yet"
        # from "no such run".
        run = await self.get_run(run_id)
        if run is None:
            raise RunNotFoundError(run_id)

        sql = (
            "SELECT * FROM events WHERE run_id = ? "
            "ORDER BY timestamp ASC, ingest_seq ASC"
        )
        params: list = [run_id]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

        cursor = await self.conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [_row_to_event(r) for r in rows]

    async def count_events_for_run(self, run_id: str) -> int:
        cursor = await self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE run_id = ?", (run_id,)
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# FastAPI dependency wiring
# ---------------------------------------------------------------------------

_db_instance: Database | None = None


def set_database(db: Database | None) -> None:
    """Install (or clear) the singleton database used by request handlers."""

    global _db_instance
    _db_instance = db


def get_database() -> Database:
    """FastAPI dependency. Resolves to the lifespan-managed `Database`."""

    if _db_instance is None:
        raise RuntimeError("Database has not been initialised")
    return _db_instance


def iter_events_in_chunks(
    events: Iterable[CognitiveEvent], chunk_size: int = 500
) -> Iterable[list[CognitiveEvent]]:
    """Helper for callers that want to break a large iterable into batches."""

    chunk: list[CognitiveEvent] = []
    for evt in events:
        chunk.append(evt)
        if len(chunk) >= chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk
