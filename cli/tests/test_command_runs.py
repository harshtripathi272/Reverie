"""Tests for ``reverie runs ...``."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner
from pytest_httpx import HTTPXMock

from reverie_cli.commands.runs import runs_group

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
        "goal": "Research observability",
        "totalEvents": 6,
        "totalTokens": 200,
        "totalToolCalls": 2,
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
        "type": "tool.called",
        "runId": RUN_ID,
        "sessionId": "22222222-2222-4222-8222-222222222222",
        "agentId": "agent-test",
        "parentId": None,
        "depth": 1,
        "timestamp": 1_700_000_000_000 + idx,
        "durationMs": None,
        "payload": {
            "_type": "tool",
            "toolName": "search_web",
            "args": {"q": "x"},
            "result": None,
            "latencyMs": 0,
            "tokenCost": None,
            "success": True,
            "errorMessage": None,
        },
        "salience": None,
        "anomaly": False,
        "schemaVersion": "1.0",
    }
    base.update(overrides)
    return base


def _strip_table_breaks(s: str) -> str:
    """Collapse Rich's column-wrapped output into a single searchable line.

    Rich may wrap a long cell across multiple physical lines, which makes
    ``in`` substring assertions brittle when the expected text spans the
    wrap boundary. We collapse all whitespace runs to single spaces so
    asserts can target the logical content.
    """

    return " ".join(s.split())


# ---------------------------------------------------------------------------
# runs list
# ---------------------------------------------------------------------------


class TestRunsList:
    def test_renders_table(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs?limit=20&offset=0",
            json={"items": [_run_payload()], "total": 1, "limit": 20, "offset": 0},
        )
        runner = CliRunner()
        result = runner.invoke(runs_group, ["list", "--backend", BASE_URL])
        assert result.exit_code == 0, result.output

        flat = _strip_table_breaks(result.output)
        # These tokens are short enough that Rich won't break them across
        # column wraps even on narrow terminals.
        assert "completed" in flat
        # The first 8 chars of the run id form the visible cell prefix.
        assert RUN_ID[:8] in flat
        # The goal column may wrap; check both whole and partial forms.
        assert "Research" in flat and "observabil" in flat

    def test_empty_list(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs?limit=20&offset=0",
            json={"items": [], "total": 0, "limit": 20, "offset": 0},
        )
        runner = CliRunner()
        result = runner.invoke(runs_group, ["list", "--backend", BASE_URL])
        assert result.exit_code == 0
        assert "no runs yet" in result.output

    def test_json_output(self, httpx_mock: HTTPXMock):
        body = {"items": [_run_payload()], "total": 1, "limit": 20, "offset": 0}
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs?limit=20&offset=0",
            json=body,
        )
        runner = CliRunner()
        result = runner.invoke(
            runs_group, ["list", "--backend", BASE_URL, "--json"]
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed == body

    def test_filters_propagate_as_query_params(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=(
                f"{BASE_URL}/api/v1/runs?limit=5&offset=2"
                "&sessionId=sess-1&status=failed"
            ),
            json={"items": [], "total": 0, "limit": 5, "offset": 2},
        )
        runner = CliRunner()
        result = runner.invoke(
            runs_group,
            [
                "list",
                "--backend",
                BASE_URL,
                "--limit",
                "5",
                "--offset",
                "2",
                "--session",
                "sess-1",
                "--status",
                "failed",
            ],
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# runs show
# ---------------------------------------------------------------------------


class TestRunsShow:
    def test_renders_run_metadata_and_events(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}",
            json=_run_payload(),
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/events?offset=0&limit=200",
            json=[_event(1), _event(2, type="tool.returned")],
        )
        runner = CliRunner()
        result = runner.invoke(
            runs_group, ["show", RUN_ID, "--backend", BASE_URL]
        )
        assert result.exit_code == 0, result.output
        flat = _strip_table_breaks(result.output)
        assert RUN_ID in flat
        assert "completed" in flat
        assert "tool.called" in flat
        assert "tool.returned" in flat

    def test_no_events_flag_skips_events_call(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}",
            json=_run_payload(),
        )
        runner = CliRunner()
        result = runner.invoke(
            runs_group,
            ["show", RUN_ID, "--backend", BASE_URL, "--no-events"],
        )
        assert result.exit_code == 0
        # We did not register an /events response; pytest-httpx would
        # complain if one were called.

    def test_unknown_run_exits_1(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}",
            status_code=404,
            json={"error": "run_not_found"},
        )
        runner = CliRunner()
        result = runner.invoke(
            runs_group, ["show", RUN_ID, "--backend", BASE_URL]
        )
        assert result.exit_code == 1
        assert "run not found" in result.output

    def test_json_output(self, httpx_mock: HTTPXMock):
        run = _run_payload()
        events = [_event(1)]
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}",
            json=run,
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/events?offset=0&limit=200",
            json=events,
        )
        runner = CliRunner()
        result = runner.invoke(
            runs_group, ["show", RUN_ID, "--backend", BASE_URL, "--json"]
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["run"] == run
        assert parsed["events"] == events
