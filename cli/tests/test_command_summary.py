"""Tests for ``reverie summary``."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner
from pytest_httpx import HTTPXMock

from reverie_cli.commands.summary import summary_command


BASE_URL = "http://test-backend:9999"
RUN_ID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def non_mocked_hosts() -> list[str]:
    return []


def _bundle_with_clusters() -> dict:
    return {
        "runId": RUN_ID,
        "nodes": [],
        "edges": [],
        "clusters": [
            {
                "id": "goal-abc",
                "label": "research",
                "rootEventId": "evt-1",
                "memberEventIds": ["evt-1", "evt-2", "evt-3"],
                "type": "goal",
            },
            {
                "id": "subagent-def",
                "label": "validator",
                "rootEventId": "evt-4",
                "memberEventIds": ["evt-4", "evt-5"],
                "type": "subagent",
            },
        ],
        "criticalPath": [],
        "summary": {
            "totalNodes": 0,
            "totalEdges": 0,
            "nodesPerZoom": {"1": 0, "2": 0, "3": 0, "4": 0},
            "anomaliesByKind": {},
            "criticalPathLength": 0,
        },
    }


# ---------------------------------------------------------------------------
# List clusters
# ---------------------------------------------------------------------------


class TestSummaryList:
    def test_lists_clusters(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/graph",
            json=_bundle_with_clusters(),
        )
        r = CliRunner().invoke(summary_command, [RUN_ID, "--backend", BASE_URL])
        assert r.exit_code == 0, r.output
        assert "research" in r.output
        assert "validator" in r.output
        assert "2 clusters" in " ".join(r.output.split())

    def test_empty_clusters_message(self, httpx_mock: HTTPXMock):
        bundle = _bundle_with_clusters()
        bundle["clusters"] = []
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/graph",
            json=bundle,
        )
        r = CliRunner().invoke(summary_command, [RUN_ID, "--backend", BASE_URL])
        assert r.exit_code == 0
        assert "no clusters" in r.output

    def test_unknown_run_exits_1(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/graph",
            status_code=404,
            json={"error": "run_not_found", "detail": ""},
        )
        r = CliRunner().invoke(summary_command, [RUN_ID, "--backend", BASE_URL])
        assert r.exit_code == 1


# ---------------------------------------------------------------------------
# Per-cluster summary
# ---------------------------------------------------------------------------


class TestSummaryFetch:
    def test_renders_ok_summary(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/clusters/goal-abc/summary",
            json={
                "runId": RUN_ID,
                "clusterId": "goal-abc",
                "memberCount": 3,
                "summary": "the agent searched and found a useful citation.",
                "status": "ok",
                "model": "claude-sonnet-4-5-20250929",
                "detail": "",
            },
        )
        r = CliRunner().invoke(
            summary_command,
            [RUN_ID, "--cluster", "goal-abc", "--backend", BASE_URL],
        )
        assert r.exit_code == 0, r.output
        assert "agent searched" in r.output

    def test_no_api_key_renders_friendly_message(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/clusters/goal-abc/summary",
            json={
                "runId": RUN_ID,
                "clusterId": "goal-abc",
                "memberCount": 3,
                "summary": "",
                "status": "no_api_key",
                "model": "claude-sonnet-4-5-20250929",
                "detail": "ANTHROPIC_API_KEY is not set",
            },
        )
        r = CliRunner().invoke(
            summary_command,
            [RUN_ID, "--cluster", "goal-abc", "--backend", BASE_URL],
        )
        assert r.exit_code == 0
        assert "ANTHROPIC_API_KEY" in r.output

    def test_refresh_flag_propagates(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/clusters/goal-abc/summary?refresh=true",
            json={
                "runId": RUN_ID,
                "clusterId": "goal-abc",
                "memberCount": 3,
                "summary": "fresh.",
                "status": "ok",
                "model": "claude-sonnet-4-5-20250929",
                "detail": "",
            },
        )
        r = CliRunner().invoke(
            summary_command,
            [RUN_ID, "--cluster", "goal-abc", "--backend", BASE_URL, "--refresh"],
        )
        assert r.exit_code == 0
        assert "fresh" in r.output

    def test_json_output(self, httpx_mock: HTTPXMock):
        body = {
            "runId": RUN_ID,
            "clusterId": "goal-abc",
            "memberCount": 3,
            "summary": "x",
            "status": "ok",
            "model": "m",
            "detail": "",
        }
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/clusters/goal-abc/summary",
            json=body,
        )
        r = CliRunner().invoke(
            summary_command,
            [RUN_ID, "--cluster", "goal-abc", "--backend", BASE_URL, "--json"],
        )
        assert r.exit_code == 0
        assert json.loads(r.output) == body
