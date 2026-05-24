"""Tests for ``reverie compare``."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner
from pytest_httpx import HTTPXMock

from reverie_cli.commands.compare import compare_command

BASE_URL = "http://test-backend:9999"
RID_A = "11111111-1111-4111-8111-111111111111"
RID_B = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def non_mocked_hosts() -> list[str]:
    return []


def _comparison_response(*, with_failure_in_b: bool = True) -> dict:
    return {
        "diff": {
            "runAId": RID_A,
            "runBId": RID_B,
            "alignmentScore": 2.4,
            "matchedCount": 3,
            "onlyACount": 0,
            "onlyBCount": 1,
            "tokenDelta": 1200,
            "durationDeltaMs": 250,
            "extraToolsInB": ["citation_lookup"],
            "missingToolsInB": [],
            "retriesInA": 0,
            "retriesInB": 2,
            "failuresInA": 0,
            "failuresInB": 1 if with_failure_in_b else 0,
            "divergence": {
                "pairIndex": 3,
                "aEventId": "evt-a-3",
                "bEventId": None,
                "reason": "event present in B but not A",
            },
        },
        "alignment": {
            "score": 2.4,
            "matchedCount": 3,
            "onlyACount": 0,
            "onlyBCount": 1,
            "pairs": [],
        },
        "faultTreeA": None,
        "faultTreeB": (
            None
            if not with_failure_in_b
            else {
                "failureEventId": "evt-b-fail",
                "chainEventIds": ["evt-b-root", "evt-b-sub", "evt-b-fail"],
                "rootEventId": "evt-b-root",
            }
        ),
        "narrative": (
            "Run B failed because the citation lookup tool was unavailable; "
            "Run A succeeded by skipping that step."
        ),
        "narrativeStatus": "ok",
    }


# ---------------------------------------------------------------------------
# CLI rendering
# ---------------------------------------------------------------------------


class TestCompareCommand:
    def test_renders_full_comparison(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/v1/compare",
            json=_comparison_response(),
        )
        r = CliRunner().invoke(
            compare_command, [RID_A, RID_B, "--backend", BASE_URL]
        )
        assert r.exit_code == 0, r.output
        flat = " ".join(r.output.split())
        # Headline numbers shown.
        assert "alignment score: 2.4" in flat
        # Divergence point called out.
        assert "Divergence at pair 3" in r.output
        # Fault tree on B rendered.
        assert "Fault tree (B)" in r.output
        assert "evt-b-fail" in r.output
        # AI narrative present.
        assert "Run B failed" in r.output

    def test_no_narrative_flag_propagates(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/v1/compare?with_narrative=false",
            json={**_comparison_response(), "narrative": "", "narrativeStatus": "skipped"},
        )
        r = CliRunner().invoke(
            compare_command,
            [RID_A, RID_B, "--backend", BASE_URL, "--no-narrative"],
        )
        assert r.exit_code == 0
        assert "skipped" in r.output

    def test_no_failures_no_fault_trees(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/v1/compare",
            json=_comparison_response(with_failure_in_b=False),
        )
        r = CliRunner().invoke(
            compare_command, [RID_A, RID_B, "--backend", BASE_URL]
        )
        assert r.exit_code == 0
        assert "Fault tree (A)" not in r.output
        assert "Fault tree (B)" not in r.output

    def test_no_divergence_renders_clean_message(self, httpx_mock: HTTPXMock):
        body = _comparison_response()
        body["diff"]["divergence"] = None
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/v1/compare",
            json=body,
        )
        r = CliRunner().invoke(
            compare_command, [RID_A, RID_B, "--backend", BASE_URL]
        )
        assert r.exit_code == 0
        assert "No divergence" in r.output

    def test_unknown_run_exits_1(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/v1/compare",
            status_code=404,
            json={"error": "run_not_found", "detail": "..."},
        )
        r = CliRunner().invoke(
            compare_command, [RID_A, RID_B, "--backend", BASE_URL]
        )
        assert r.exit_code == 1

    def test_json_output(self, httpx_mock: HTTPXMock):
        body = _comparison_response()
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/v1/compare",
            json=body,
        )
        r = CliRunner().invoke(
            compare_command,
            [RID_A, RID_B, "--backend", BASE_URL, "--json"],
        )
        assert r.exit_code == 0
        assert json.loads(r.output) == body
