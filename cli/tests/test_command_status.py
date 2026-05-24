"""Tests for ``reverie status``."""

from __future__ import annotations

import httpx
import pytest
from click.testing import CliRunner
from pytest_httpx import HTTPXMock

from reverie_cli.commands.status import status_command

BASE_URL = "http://test-backend:9999"


@pytest.fixture
def non_mocked_hosts() -> list[str]:
    return []


def test_status_ok(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/health",
        json={"status": "ok", "version": "0.1.0", "dbUserVersion": 1},
    )
    runner = CliRunner()
    result = runner.invoke(status_command, ["--backend", BASE_URL])
    assert result.exit_code == 0, result.output
    assert "ok" in result.output
    assert "0.1.0" in result.output
    assert "schema v1" in result.output


def test_status_unreachable_exits_1(httpx_mock: HTTPXMock):
    httpx_mock.add_exception(
        httpx.ConnectError("connection refused"),
        url=f"{BASE_URL}/health",
    )
    runner = CliRunner()
    result = runner.invoke(status_command, ["--backend", BASE_URL])
    assert result.exit_code == 1
    assert "cannot reach" in result.output


def test_status_5xx_exits_1(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/health",
        status_code=500,
        json={"error": "boom"},
    )
    runner = CliRunner()
    result = runner.invoke(status_command, ["--backend", BASE_URL])
    assert result.exit_code == 1
