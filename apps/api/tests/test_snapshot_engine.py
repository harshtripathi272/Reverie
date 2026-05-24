"""Tests for the DB-aware ``SnapshotEngine``.

These exercise checkpoint creation, range guards, terminal-state shortcut,
and the LRU. Use the same in-process app fixture as the route tests so the
DB is real (SQLite WAL on a tmp file).
"""

from __future__ import annotations

import pytest

from reverie_api.db import RunNotFoundError
from reverie_api.snapshot import (
    CHECKPOINT_INTERVAL,
    SnapshotEngine,
    SnapshotNotFoundError,
)

from .conftest import (
    goal_event,
    make_event,
    make_run_create,
    make_uuid,
    retry_event,
    subagent_event,
    tool_returned_event,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed(client, count: int = 12) -> str:
    """Create a run and ingest ``count`` events. Return the run id."""

    body = make_run_create()
    r = await client.post("/api/v1/runs", json=body)
    assert r.status_code == 201
    rid = body["runId"]

    batch = []
    # Mix: 1 goal.created, then alternating tool.called/tool.returned.
    batch.append(goal_event(rid, timestamp=1_700_000_000_000))
    for i in range(1, count):
        if i % 2 == 1:
            batch.append(make_event(rid, timestamp=1_700_000_000_000 + i))  # tool.called
        else:
            batch.append(
                tool_returned_event(rid, timestamp=1_700_000_000_000 + i, token_cost=10)
            )
    r = await client.post("/api/v1/events/batch", json=batch)
    assert r.status_code == 201
    return rid


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class TestStateAt:
    async def test_at_zero_is_empty_state(self, app, client):
        rid = await _seed(client, count=4)
        engine: SnapshotEngine = app.state.snapshot_engine
        s = await engine.state_at(rid, at=0)
        assert s.event_count == 0
        assert s.last_event_id is None
        assert s.run_id == rid

    async def test_at_terminal_matches_full_fold(self, app, client):
        rid = await _seed(client, count=6)
        engine: SnapshotEngine = app.state.snapshot_engine
        s = await engine.state_at(rid, at=6)
        assert s.event_count == 6
        # 1 goal created + 3 tool.called + 2 tool.returned, no goal.completed
        # => total_tool_calls counts tool.called events only.
        assert s.total_tool_calls == 3
        # Two tool.returned each carrying token_cost=10.
        assert s.total_tokens == 20

    async def test_intermediate_state_truncates_correctly(self, app, client):
        rid = await _seed(client, count=6)
        engine: SnapshotEngine = app.state.snapshot_engine
        s = await engine.state_at(rid, at=3)
        # Events: [goal.created, tool.called, tool.returned] only.
        assert s.event_count == 3
        assert s.total_tool_calls == 1
        assert s.total_tokens == 10  # one tool.returned with token_cost=10
        assert len(s.active_goals) == 1  # goal still active

    async def test_unknown_run_raises(self, app):
        engine: SnapshotEngine = app.state.snapshot_engine
        with pytest.raises(RunNotFoundError):
            await engine.state_at(make_uuid(), at=0)

    async def test_out_of_range_raises(self, app, client):
        rid = await _seed(client, count=4)
        engine: SnapshotEngine = app.state.snapshot_engine
        with pytest.raises(SnapshotNotFoundError):
            await engine.state_at(rid, at=999)
        with pytest.raises(SnapshotNotFoundError):
            await engine.state_at(rid, at=-1)


class TestCheckpoints:
    async def test_no_checkpoint_when_below_interval(self, app, client):
        rid = await _seed(client, count=10)  # < CHECKPOINT_INTERVAL
        engine: SnapshotEngine = app.state.snapshot_engine
        await engine.state_at(rid, at=10)

        cursor = await app.state.db.conn.execute(
            "SELECT COUNT(*) FROM run_checkpoints WHERE run_id = ?", (rid,)
        )
        row = await cursor.fetchone()
        assert int(row[0]) == 0

    async def test_checkpoint_persisted_when_crossing_interval(self, app, client):
        # Need a run with > CHECKPOINT_INTERVAL events to trigger persistence.
        body = make_run_create()
        r = await client.post("/api/v1/runs", json=body)
        assert r.status_code == 201
        rid = body["runId"]

        n = CHECKPOINT_INTERVAL + 5  # 55
        events = [
            goal_event(rid, timestamp=1_700_000_000_000),
            *[
                make_event(rid, timestamp=1_700_000_000_000 + i)
                for i in range(1, n)
            ],
        ]
        # Insert in two batches so we don't exceed the 1000-event API cap
        # (we won't here, but it's a habit worth keeping).
        await client.post("/api/v1/events/batch", json=events[:30])
        await client.post("/api/v1/events/batch", json=events[30:])

        engine: SnapshotEngine = app.state.snapshot_engine
        s = await engine.state_at(rid, at=n)
        assert s.event_count == n

        cursor = await app.state.db.conn.execute(
            "SELECT event_count FROM run_checkpoints WHERE run_id = ? "
            "ORDER BY event_count DESC LIMIT 1",
            (rid,),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert int(row[0]) == n  # we store at the *current* event_count

    async def test_checkpoint_cached_state_skips_reload(self, app, client):
        rid = await _seed(client, count=8)
        engine: SnapshotEngine = app.state.snapshot_engine

        s1 = await engine.state_at(rid, at=5)
        s2 = await engine.state_at(rid, at=5)
        # Same logical content; LRU may return the same instance or a fresh
        # equal one — either is acceptable for correctness.
        assert s1 == s2

    async def test_invalidate_run_drops_checkpoints(self, app, client):
        body = make_run_create()
        await client.post("/api/v1/runs", json=body)
        rid = body["runId"]
        # Force a checkpoint by ingesting > CHECKPOINT_INTERVAL events.
        n = CHECKPOINT_INTERVAL + 1
        events = [
            goal_event(rid, timestamp=i) for i in range(n)
        ]
        # Distinct ids are guaranteed by goal_event's default UUID generator.
        await client.post("/api/v1/events/batch", json=events)

        engine: SnapshotEngine = app.state.snapshot_engine
        await engine.state_at(rid, at=n)

        await engine.invalidate_run(rid)
        cursor = await app.state.db.conn.execute(
            "SELECT COUNT(*) FROM run_checkpoints WHERE run_id = ?", (rid,)
        )
        assert int((await cursor.fetchone())[0]) == 0


class TestFirstFailureIndex:
    async def test_returns_none_when_no_failures(self, app, client):
        rid = await _seed(client, count=4)
        engine: SnapshotEngine = app.state.snapshot_engine
        assert await engine.first_failure_index(rid) is None

    async def test_finds_first_failure(self, app, client):
        body = make_run_create()
        await client.post("/api/v1/runs", json=body)
        rid = body["runId"]

        # Sequence: goal, tool.called, tool.returned, retry.exhausted, tool.called
        events = [
            goal_event(rid, timestamp=1),
            make_event(rid, timestamp=2),
            tool_returned_event(rid, timestamp=3),
            retry_event(rid, event_type="retry.exhausted", timestamp=4),
            make_event(rid, timestamp=5),
        ]
        await client.post("/api/v1/events/batch", json=events)

        engine: SnapshotEngine = app.state.snapshot_engine
        idx = await engine.first_failure_index(rid)
        assert idx == 4  # 1-based; the retry.exhausted event

    async def test_unknown_run_raises(self, app):
        engine: SnapshotEngine = app.state.snapshot_engine
        with pytest.raises(RunNotFoundError):
            await engine.first_failure_index(make_uuid())


class TestLRU:
    async def test_lru_does_not_grow_unbounded(self, app, client):
        rid = await _seed(client, count=10)
        # Tiny LRU for the test.
        engine = SnapshotEngine(app.state.db, lru_size=3)

        for at in range(1, 11):
            await engine.state_at(rid, at=at)

        # LRU caps at 3 entries.
        assert len(engine._lru) == 3
