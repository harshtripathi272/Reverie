"""Test fixtures.

Each test gets a fresh FastAPI app bound to a fresh SQLite file under a
``tmp_path``. We use FastAPI's lifespan via httpx's ASGITransport so the app
lifecycle (DB connect, migrations, broker init) runs the same way it does
under uvicorn.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

from reverie_api.config import Settings
from reverie_api.main import create_app


@pytest.fixture(scope="session")
def event_loop():
    """Single asyncio loop for the test session, since the app holds a
    long-lived `aiosqlite.Connection` keyed to its loop."""

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def settings(tmp_path) -> Settings:
    db_file = tmp_path / "reverie-test.db"
    return Settings(
        db_path=db_file,
        host="127.0.0.1",
        port=0,
        cors_origins=["http://localhost:3000"],
        env="development",
    )


@pytest_asyncio.fixture
async def app(settings):
    instance = create_app(settings)
    async with instance.router.lifespan_context(instance):
        yield instance


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_uuid() -> str:
    return str(uuid.uuid4())


def make_run_create(**overrides) -> dict:
    base = {
        "runId": make_uuid(),
        "sessionId": make_uuid(),
        "agentId": "agent-test",
        "runtime": "openai-agents",
        "startedAt": 1_700_000_000_000,
        "goal": "Test run",
    }
    base.update(overrides)
    return base


def make_event(
    run_id: str,
    *,
    event_type: str = "tool.called",
    payload: dict | None = None,
    **overrides,
) -> dict:
    if payload is None:
        payload = {
            "_type": "tool",
            "toolName": "search_web",
            "args": {"query": "x"},
            "result": None,
            "latencyMs": 0,
            "tokenCost": None,
            "success": True,
            "errorMessage": None,
        }
    base = {
        "id": make_uuid(),
        "type": event_type,
        "runId": run_id,
        "sessionId": "session-test",
        "agentId": "agent-test",
        "parentId": None,
        "depth": 0,
        "timestamp": 1_700_000_000_001,
        "durationMs": None,
        "payload": payload,
        "salience": None,
        "anomaly": False,
        "schemaVersion": "1.0",
    }
    base.update(overrides)
    return base


def goal_event(run_id: str, **overrides) -> dict:
    return make_event(
        run_id,
        event_type="goal.created",
        payload={
            "_type": "goal",
            "intent": "test goal",
            "priority": "high",
            "context": "",
        },
        **overrides,
    )


def tool_returned_event(run_id: str, *, token_cost: int = 100, **overrides) -> dict:
    return make_event(
        run_id,
        event_type="tool.returned",
        payload={
            "_type": "tool",
            "toolName": "search_web",
            "args": {"query": "x"},
            "result": {"hits": 3},
            "latencyMs": 42.5,
            "tokenCost": token_cost,
            "success": True,
            "errorMessage": None,
        },
        **overrides,
    )


def retry_event(run_id: str, *, event_type: str = "retry.triggered", **overrides) -> dict:
    return make_event(
        run_id,
        event_type=event_type,
        payload={
            "_type": "retry",
            "reason": "timeout",
            "attempt": 2,
            "maxAttempts": 3,
            "previousError": "ECONNRESET",
            "backoffMs": 500,
        },
        **overrides,
    )


def subagent_event(run_id: str, **overrides) -> dict:
    return make_event(
        run_id,
        event_type="subagent.spawned",
        payload={
            "_type": "subagent",
            "agentType": "researcher",
            "task": "find sources",
            "delegatedGoalId": None,
            "childRunId": None,
        },
        **overrides,
    )
