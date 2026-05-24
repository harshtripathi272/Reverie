"""Tests for ``reverie replay``."""

from __future__ import annotations

import pytest
from click.testing import CliRunner
from pytest_httpx import HTTPXMock

from reverie_cli.commands.replay import replay_command

BASE_URL = "http://test-backend:9999"
RUN_ID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def non_mocked_hosts() -> list[str]:
    return []


def _run_payload(**overrides) -> dict:
    base = {
        "id": RUN_ID,
        "sessionId": "22222222-2222-4222-8222-222222222222",
        "agentId": "agent-test",
        "runtime": "openai-agents",
        "startedAt": 1_700_000_000_000,
        "completedAt": 1_700_000_001_500,
        "status": "completed",
        "goal": "Research",
        "totalEvents": 0,
        "totalTokens": 0,
        "totalToolCalls": 0,
        "totalRetries": 0,
        "totalSubagents": 0,
        "pinned": False,
        "tags": [],
        "createdAt": 1_700_000_000_000,
    }
    base.update(overrides)
    return base


def _event(idx: int, **overrides) -> dict:
    base = {
        "id": f"00000000-0000-4000-8000-{idx:012x}",
        "type": "goal.created",
        "runId": RUN_ID,
        "sessionId": "22222222-2222-4222-8222-222222222222",
        "agentId": "agent-test",
        "parentId": None,
        "depth": 0,
        "timestamp": 1_700_000_000_000 + idx,
        "durationMs": None,
        "payload": {
            "_type": "goal",
            "intent": f"step {idx}",
            "priority": "high",
            "context": "",
        },
        "salience": None,
        "anomaly": False,
        "schemaVersion": "1.0",
    }
    base.update(overrides)
    return base


def test_replay_streams_events(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/api/v1/runs/{RUN_ID}",
        json=_run_payload(),
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/events?offset=0&limit=10000",
        json=[_event(1), _event(2, type="tool.called")],
    )
    runner = CliRunner()
    result = runner.invoke(replay_command, [RUN_ID, "--backend", BASE_URL])
    assert result.exit_code == 0, result.output
    assert "Replaying" in result.output
    assert "goal.created" in result.output
    assert "tool.called" in result.output


def test_replay_unknown_run_returns_1(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/api/v1/runs/{RUN_ID}",
        status_code=404,
        json={"error": "run_not_found"},
    )
    runner = CliRunner()
    result = runner.invoke(replay_command, [RUN_ID, "--backend", BASE_URL])
    assert result.exit_code == 1
    assert "run not found" in result.output


def test_replay_with_no_events(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/api/v1/runs/{RUN_ID}",
        json=_run_payload(),
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/events?offset=0&limit=10000",
        json=[],
    )
    runner = CliRunner()
    result = runner.invoke(replay_command, [RUN_ID, "--backend", BASE_URL])
    assert result.exit_code == 0
    assert "no events" in result.output
