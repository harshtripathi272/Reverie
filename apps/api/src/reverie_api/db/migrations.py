"""SQLite schema migrations.

We use ``PRAGMA user_version`` as a tiny built-in migration counter. Each
migration is a function that takes a connection and brings the schema from
``user_version = N - 1`` to ``user_version = N``.

This deliberately avoids Alembic for Phase 0 — SQLite-only, single file,
single writer, additive-only schema changes are all we need.

When you add a migration:
  1. Append a new ``async def _migration_NNN(...)`` function.
  2. Append it to ``MIGRATIONS`` in order.
  3. Never re-order or rewrite a past migration.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import aiosqlite

Migration = Callable[[aiosqlite.Connection], Awaitable[None]]


async def _migration_001_initial_schema(conn: aiosqlite.Connection) -> None:
    """Create the ``runs`` and ``events`` tables and supporting indexes."""

    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            runtime TEXT NOT NULL,
            started_at INTEGER NOT NULL,
            completed_at INTEGER,
            status TEXT NOT NULL DEFAULT 'running'
                CHECK (status IN ('running', 'completed', 'failed', 'aborted')),
            goal TEXT,
            total_events INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            total_tool_calls INTEGER NOT NULL DEFAULT 0,
            total_retries INTEGER NOT NULL DEFAULT 0,
            total_subagents INTEGER NOT NULL DEFAULT 0,
            pinned INTEGER NOT NULL DEFAULT 0,
            tags TEXT NOT NULL DEFAULT '[]',
            created_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s', 'now') AS INTEGER) * 1000)
        );

        CREATE INDEX IF NOT EXISTS idx_runs_session_id ON runs(session_id);
        CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at);
        CREATE INDEX IF NOT EXISTS idx_runs_status     ON runs(status);

        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            session_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            parent_id TEXT REFERENCES events(id) ON DELETE SET NULL,
            depth INTEGER NOT NULL DEFAULT 0,
            timestamp INTEGER NOT NULL,
            duration_ms REAL,
            payload TEXT NOT NULL,
            salience REAL,
            anomaly INTEGER NOT NULL DEFAULT 0,
            schema_version TEXT NOT NULL DEFAULT '1.0',
            -- Append-only: the order events arrive at the API. Used for stable
            -- pagination when many events share a millisecond timestamp.
            ingest_seq INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_events_run_id    ON events(run_id);
        CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
        CREATE INDEX IF NOT EXISTS idx_events_parent_id ON events(parent_id);
        CREATE INDEX IF NOT EXISTS idx_events_type      ON events(type);
        CREATE INDEX IF NOT EXISTS idx_events_run_seq   ON events(run_id, ingest_seq);
        """
    )


async def _migration_002_run_checkpoints(conn: aiosqlite.Connection) -> None:
    """Create the ``run_checkpoints`` table for the snapshot engine.

    Each row is a fully-folded :class:`RunState` JSON at a specific
    ``event_count`` for a run. The engine creates these lazily on replay so
    ingestion stays in the < 5ms p50 budget.
    """

    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS run_checkpoints (
            run_id      TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            event_count INTEGER NOT NULL,
            state_json  TEXT NOT NULL,
            created_at  INTEGER NOT NULL,
            PRIMARY KEY (run_id, event_count)
        );

        CREATE INDEX IF NOT EXISTS idx_run_checkpoints_run_id_count
          ON run_checkpoints(run_id, event_count);
        """
    )


async def _migration_003_ai_summaries(conn: aiosqlite.Connection) -> None:
    """Create the ``ai_summaries`` cache for Claude-generated text.

    Keyed by ``(scope, scope_id, content_hash)`` so identical regions reuse
    the same row. ``scope`` is "cluster" for Phase 3 and "comparison" for
    Phase 4.
    """

    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_summaries (
            scope         TEXT NOT NULL,
            scope_id      TEXT NOT NULL,
            content_hash  TEXT NOT NULL,
            text          TEXT NOT NULL,
            status        TEXT NOT NULL,
            model         TEXT NOT NULL,
            created_at    INTEGER NOT NULL,
            PRIMARY KEY (scope, scope_id, content_hash)
        );

        CREATE INDEX IF NOT EXISTS idx_ai_summaries_scope
          ON ai_summaries(scope, scope_id);
        """
    )


MIGRATIONS: list[Migration] = [
    _migration_001_initial_schema,
    _migration_002_run_checkpoints,
    _migration_003_ai_summaries,
]


async def apply_migrations(conn: aiosqlite.Connection) -> int:
    """Apply any pending migrations. Returns the new ``user_version``.

    Runs every migration in a single transaction — partial application is
    impossible.
    """

    cursor = await conn.execute("PRAGMA user_version")
    row = await cursor.fetchone()
    current = int(row[0]) if row else 0
    target = len(MIGRATIONS)

    if current > target:
        raise RuntimeError(
            f"database user_version={current} is newer than this code "
            f"(target={target}). Refusing to downgrade."
        )

    if current == target:
        return current

    pending = MIGRATIONS[current:]
    await conn.execute("BEGIN IMMEDIATE")
    try:
        for migration in pending:
            await migration(conn)
        await conn.execute(f"PRAGMA user_version = {target}")
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise

    return target
