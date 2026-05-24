"""Tests for ``reverie graph`` / ``anomalies`` / ``zoom``."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner
from pytest_httpx import HTTPXMock

from reverie_cli.commands.graph import (
    anomalies_command,
    graph_command,
    zoom_command,
)

BASE_URL = "http://test-backend:9999"
RUN_ID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def non_mocked_hosts() -> list[str]:
    return []


def _node(
    nid: str,
    *,
    type_: str = "tool.called",
    parent: str | None = None,
    depth: int = 1,
    ts: int = 1,
    label: str = "",
    zoom: int = 3,
    on_critical_path: bool = False,
    anomalies: list[dict] | None = None,
) -> dict:
    return {
        "id": nid,
        "type": type_,
        "parentId": parent,
        "depth": depth,
        "timestamp": ts,
        "durationMs": None,
        "salience": None,
        "anomaly": False,
        "zoomLevel": zoom,
        "anomalies": anomalies or [],
        "cluster": None,
        "onCriticalPath": on_critical_path,
        "label": label or type_,
    }


def _bundle(**overrides) -> dict:
    base = {
        "runId": RUN_ID,
        "nodes": [
            _node("a", type_="goal.created", parent=None, depth=0, ts=1, label="mission", zoom=1, on_critical_path=True),
            _node("b", type_="tool.called", parent="a", depth=1, ts=2, label="search_web", zoom=3),
            _node("c", type_="tool.returned", parent="a", depth=1, ts=3, label="search_web", zoom=3),
        ],
        "edges": [
            {"source": "a", "target": "b", "onCriticalPath": False},
            {"source": "a", "target": "c", "onCriticalPath": False},
        ],
        "clusters": [],
        "criticalPath": ["a"],
        "summary": {
            "totalNodes": 3,
            "totalEdges": 2,
            "nodesPerZoom": {"1": 1, "2": 0, "3": 2, "4": 0},
            "anomaliesByKind": {},
            "criticalPathLength": 1,
        },
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------


class TestGraphCommand:
    def test_renders_tree(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/graph",
            json=_bundle(),
        )
        result = CliRunner().invoke(graph_command, [RUN_ID, "--backend", BASE_URL])
        assert result.exit_code == 0, result.output
        flat = " ".join(result.output.split())
        assert "3 nodes, 2 edges" in flat
        assert "mission" in flat
        assert "search_web" in flat

    def test_level_query_param_propagates(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/graph?level=1",
            json=_bundle(
                nodes=[_bundle()["nodes"][0]],
                edges=[],
                summary={
                    "totalNodes": 1,
                    "totalEdges": 0,
                    "nodesPerZoom": {"1": 1, "2": 0, "3": 0, "4": 0},
                    "anomaliesByKind": {},
                    "criticalPathLength": 1,
                },
            ),
        )
        result = CliRunner().invoke(
            graph_command, [RUN_ID, "--backend", BASE_URL, "--level", "1"]
        )
        assert result.exit_code == 0
        assert "1 nodes" in " ".join(result.output.split())

    def test_invalid_level_rejected(self):
        # Click range guard — no HTTP call should happen.
        result = CliRunner().invoke(graph_command, [RUN_ID, "--level", "7"])
        assert result.exit_code != 0

    def test_unknown_run_exits_1(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/graph",
            status_code=404,
            json={"error": "run_not_found", "detail": f"run not found: {RUN_ID}"},
        )
        result = CliRunner().invoke(graph_command, [RUN_ID, "--backend", BASE_URL])
        assert result.exit_code == 1
        assert "run_not_found" in result.output

    def test_json_output(self, httpx_mock: HTTPXMock):
        body = _bundle()
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/graph",
            json=body,
        )
        result = CliRunner().invoke(
            graph_command, [RUN_ID, "--backend", BASE_URL, "--json"]
        )
        assert result.exit_code == 0
        assert json.loads(result.output) == body


# ---------------------------------------------------------------------------
# anomalies
# ---------------------------------------------------------------------------


class TestAnomaliesCommand:
    def test_empty_list_message(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/anomalies",
            json=[],
        )
        result = CliRunner().invoke(
            anomalies_command, [RUN_ID, "--backend", BASE_URL]
        )
        assert result.exit_code == 0
        assert "no anomalies" in result.output

    def test_renders_grouped_by_kind(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/anomalies",
            json=[
                {
                    "eventId": "n1",
                    "eventType": "tool.called",
                    "label": "search",
                    "timestamp": 1,
                    "kind": "loop",
                    "severity": "warning",
                    "detail": "identical search call repeated within 60s",
                },
                {
                    "eventId": "n2",
                    "eventType": "tool.called",
                    "label": "search",
                    "timestamp": 10,
                    "kind": "loop",
                    "severity": "warning",
                    "detail": "identical search call repeated within 60s",
                },
            ],
        )
        result = CliRunner().invoke(
            anomalies_command, [RUN_ID, "--backend", BASE_URL]
        )
        assert result.exit_code == 0
        assert "loop" in result.output
        assert "60s" in result.output

    def test_kind_filter(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/anomalies",
            json=[
                {
                    "eventId": "n1",
                    "eventType": "tool.returned",
                    "label": "x",
                    "timestamp": 1,
                    "kind": "hotspot",
                    "severity": "warning",
                    "detail": "a lot of tokens",
                },
                {
                    "eventId": "n2",
                    "eventType": "tool.called",
                    "label": "x",
                    "timestamp": 2,
                    "kind": "loop",
                    "severity": "warning",
                    "detail": "loop",
                },
            ],
        )
        result = CliRunner().invoke(
            anomalies_command,
            [RUN_ID, "--backend", BASE_URL, "--kind", "hotspot"],
        )
        assert result.exit_code == 0
        assert "hotspot" in result.output
        # Loop should be filtered out — but the legend contains the word
        # "loop" sometimes; check by the count line.
        # Just verify the count is 1, not 2.
        assert "1 anomalies" in " ".join(result.output.split())


# ---------------------------------------------------------------------------
# zoom
# ---------------------------------------------------------------------------


class TestZoomCommand:
    def test_renders_distribution(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/graph",
            json=_bundle(
                summary={
                    "totalNodes": 100,
                    "totalEdges": 99,
                    "nodesPerZoom": {"1": 1, "2": 4, "3": 30, "4": 65},
                    "anomaliesByKind": {},
                    "criticalPathLength": 4,
                },
            ),
        )
        result = CliRunner().invoke(zoom_command, [RUN_ID, "--backend", BASE_URL])
        assert result.exit_code == 0
        flat = " ".join(result.output.split())
        # All four levels present.
        assert "L1" in flat and "L2" in flat and "L3" in flat and "L4" in flat
        # Counts present.
        assert " 1 " in flat
        assert " 65 " in flat

    def test_json_output(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/v1/runs/{RUN_ID}/graph",
            json=_bundle(),
        )
        result = CliRunner().invoke(
            zoom_command, [RUN_ID, "--backend", BASE_URL, "--json"]
        )
        assert result.exit_code == 0
        body = json.loads(result.output)
        assert body["totalNodes"] == 3
        assert "L1_mission" in body["perZoom"]
        assert body["perZoom"]["L1_mission"] == 1
        assert body["perZoom"]["L3_operation"] == 2
