"""Tests for ``reverie state`` and the new ``replay --jump-failure`` flag."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner
from pytest_httpx import HTTPXMock

from reverie_cli.commands.replay import replay_command
from reverie_cli.commands.state import state_command

BASE_URL = "http://test-backend:9999"
RUN_ID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def non_mocked_hosts() -> list[str]:
    return []


def _state_payload(**overrides) -> dict:
    base = {
        "runId": RUN_ID,
        "eventCount": 5,
        "lastEventId": "00000000-0000-4000-8000-000000000005",
        "lastTimestamp": 1_700_000_000_005,
        "activeGoals": [
            {
                "eventId": "00000000-0000-4000-8000-000000000001",
                "intent": "research the topic",
                "priority": "high",
                "parentId": None,
                "depth": 0,
                "startedAt": 1_700_000_000_000,
            }
        ],
        "activeTools": [],
        "recentToolResults": [
            {
                "eventId": "00000000-0000-4000-8000-000000000003",
                "toolName": "search_web",
                "success": True,
                "latencyMs": 42.5,
                "errorMessage": None,
                "finishedAt": 1_700_000_000_003,
            }
        ],
        "totalTokens": 120,
        "totalToolCalls": 1,
        "totalRetries": 0,
        "totalSubagents": 0,
        "totalFailures": 0,
        "completedGoals": [],
        "failedGoals": [],
        "firstFailure": None,
        "lastReasoningSummary": None,
        "lastReasoningModel": None,
        "contextTokensUsed": 0,
        "contextTokenLimit": 0,
        "contextPercentUsed": 0.0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# state command
# ---------------------------------------------------------------------------


class TestStateCommand:
    def test_renders_terminal_state(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/snapshot",
            json=_state_payload(),
        )
        runner = CliRunner()
        result = runner.invoke(state_command, [RUN_ID, "--backend", BASE_URL])
        assert result.exit_code == 0, result.output
        assert "research the topic" in " ".join(result.output.split())
        assert "search_web" in result.output
        assert "events=5" in " ".join(result.output.split())

    def test_renders_state_at_specific_index(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/snapshot?at=2",
            json=_state_payload(eventCount=2),
        )
        runner = CliRunner()
        result = runner.invoke(
            state_command, [RUN_ID, "--at", "2", "--backend", BASE_URL]
        )
        assert result.exit_code == 0
        assert "event 2" in " ".join(result.output.split())

    def test_unknown_run_exits_1(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/snapshot",
            status_code=404,
            json={"error": "run_not_found", "detail": f"run not found: {RUN_ID}"},
        )
        runner = CliRunner()
        result = runner.invoke(state_command, [RUN_ID, "--backend", BASE_URL])
        assert result.exit_code == 1
        assert "run_not_found" in result.output

    def test_out_of_range_exits_1(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/snapshot?at=999",
            status_code=404,
            json={
                "error": "snapshot_out_of_range",
                "detail": "snapshot at=999 is out of range",
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            state_command, [RUN_ID, "--at", "999", "--backend", BASE_URL]
        )
        assert result.exit_code == 1
        assert "snapshot_out_of_range" in result.output

    def test_json_output(self, httpx_mock: HTTPXMock):
        body = _state_payload()
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/snapshot",
            json=body,
        )
        runner = CliRunner()
        result = runner.invoke(
            state_command, [RUN_ID, "--backend", BASE_URL, "--json"]
        )
        assert result.exit_code == 0
        assert json.loads(result.output) == body

    def test_renders_failure_summary(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/snapshot",
            json=_state_payload(
                totalFailures=1,
                firstFailure={
                    "eventId": "00000000-0000-4000-8000-000000000004",
                    "type": "tool.failed",
                    "message": "tool.failed: timeout",
                    "occurredAt": 1_700_000_000_004,
                },
            ),
        )
        runner = CliRunner()
        result = runner.invoke(state_command, [RUN_ID, "--backend", BASE_URL])
        assert result.exit_code == 0
        assert "first failure" in " ".join(result.output.split())
        assert "tool.failed" in result.output


# ---------------------------------------------------------------------------
# replay --jump-failure
# ---------------------------------------------------------------------------


def _run_payload(**overrides) -> dict:
    base = {
        "id": RUN_ID,
        "sessionId": "22222222-2222-4222-8222-222222222222",
        "agentId": "agent-test",
        "runtime": "openai-agents",
        "startedAt": 1_700_000_000_000,
        "completedAt": 1_700_000_001_500,
        "status": "completed",
        "goal": "test",
        "totalEvents": 5,
        "totalTokens": 0,
        "totalToolCalls": 1,
        "totalRetries": 0,
        "totalSubagents": 0,
        "pinned": False,
        "tags": [],
        "createdAt": 1_700_000_000_000,
    }
    base.update(overrides)
    return base


def _events(count: int, fail_at: int | None = None) -> list[dict]:
    out = []
    for i in range(1, count + 1):
        type_ = (
            "tool.failed"
            if fail_at is not None and i == fail_at
            else "tool.called"
            if i % 2 == 1
            else "tool.returned"
        )
        payload = {
            "_type": "tool",
            "toolName": f"step_{i}",
            "args": {},
            "result": None,
            "latencyMs": 10.0,
            "tokenCost": None,
            "success": type_ != "tool.failed",
            "errorMessage": "boom" if type_ == "tool.failed" else None,
        }
        out.append(
            {
                "id": f"00000000-0000-4000-8000-{i:012x}",
                "type": type_,
                "runId": RUN_ID,
                "sessionId": "22222222-2222-4222-8222-222222222222",
                "agentId": "agent-test",
                "parentId": None,
                "depth": 1,
                "timestamp": 1_700_000_000_000 + i,
                "durationMs": None,
                "payload": payload,
                "salience": None,
                "anomaly": False,
                "schemaVersion": "1.0",
            }
        )
    return out


class TestReplayJumpFailure:
    def test_jumps_to_failure_index(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}",
            json=_run_payload(),
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/events?offset=0&limit=10000",
            json=_events(5, fail_at=4),
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/failures",
            json={
                "index": 4,
                "event": {},
                "stateBefore": {},
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            replay_command,
            [RUN_ID, "--backend", BASE_URL, "--jump-failure"],
        )
        assert result.exit_code == 0, result.output
        assert "FAILURE" in result.output
        assert "tool.failed" in result.output
        # Only events up to the failure index should appear (4 of 5).
        assert "step_5" not in result.output

    def test_no_failures_prints_message(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}",
            json=_run_payload(),
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/events?offset=0&limit=10000",
            json=_events(5),
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/failures",
            status_code=404,
            json={"error": "no_failures"},
        )
        runner = CliRunner()
        result = runner.invoke(
            replay_command,
            [RUN_ID, "--backend", BASE_URL, "--jump-failure"],
        )
        assert result.exit_code == 0
        assert "no failures" in result.output

    def test_to_index_truncates(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}",
            json=_run_payload(),
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/events?offset=0&limit=10000",
            json=_events(5),
        )
        runner = CliRunner()
        result = runner.invoke(
            replay_command, [RUN_ID, "--backend", BASE_URL, "--to", "3"]
        )
        assert result.exit_code == 0
        assert "step_3" in result.output
        assert "step_4" not in result.output
