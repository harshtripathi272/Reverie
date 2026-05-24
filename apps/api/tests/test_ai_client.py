"""Tests for the Claude client wrapper (substep 3.2).

We never make real Claude calls — pytest-httpx mocks the API.
"""

from __future__ import annotations

import httpx
import pytest
from pytest_httpx import HTTPXMock

from reverie_api.ai.client import (
    DEFAULT_API_URL,
    PROMPT_HARD_CAP_CHARS,
    ClaudeClient,
    SummaryResult,
    _trim_to_cap,
)


@pytest.fixture
def non_mocked_hosts() -> list[str]:
    return []


# ---------------------------------------------------------------------------
# Configured / unconfigured behaviour
# ---------------------------------------------------------------------------


class TestConfigured:
    def test_no_api_key_returns_placeholder(self):
        client = ClaudeClient(api_key="")
        assert client.is_configured is False

    def test_with_api_key_is_configured(self):
        client = ClaudeClient(api_key="sk-test")
        assert client.is_configured is True

    def test_disabled_short_circuits(self):
        client = ClaudeClient(api_key="sk-test", disabled=True)
        assert client.is_configured is False


# ---------------------------------------------------------------------------
# Async summarize() error paths
# ---------------------------------------------------------------------------


class TestSummarizeErrorPaths:
    async def test_no_key_returns_no_api_key_status(self, httpx_mock: HTTPXMock):
        client = ClaudeClient(api_key="")
        result = await client.summarize(system="be brief", user="hi")
        assert result.status == "no_api_key"
        assert result.text == ""
        # No HTTP call should be made.
        assert len(httpx_mock.get_requests()) == 0

    async def test_disabled_returns_disabled_status(self, httpx_mock: HTTPXMock):
        client = ClaudeClient(api_key="sk-test", disabled=True)
        result = await client.summarize(system="x", user="y")
        assert result.status == "disabled"
        assert len(httpx_mock.get_requests()) == 0

    async def test_429_returns_rate_limited(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=DEFAULT_API_URL,
            status_code=429,
            json={"error": {"type": "rate_limit_error"}},
        )
        client = ClaudeClient(api_key="sk-test")
        result = await client.summarize(system="x", user="y")
        assert result.status == "rate_limited"

    async def test_500_returns_api_error(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=DEFAULT_API_URL,
            status_code=500,
            json={"error": "boom"},
        )
        client = ClaudeClient(api_key="sk-test")
        result = await client.summarize(system="x", user="y")
        assert result.status == "api_error"

    async def test_network_error_returns_api_error(self, httpx_mock: HTTPXMock):
        httpx_mock.add_exception(
            httpx.ConnectError("connection refused"),
            url=DEFAULT_API_URL,
        )
        client = ClaudeClient(api_key="sk-test")
        result = await client.summarize(system="x", user="y")
        assert result.status == "api_error"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestSummarizeHappyPath:
    async def test_extracts_text_from_response(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=DEFAULT_API_URL,
            json={
                "content": [
                    {"type": "text", "text": "the agent looped on the search tool."}
                ],
            },
        )
        client = ClaudeClient(api_key="sk-test")
        result = await client.summarize(system="be brief", user="...")
        assert result.is_ok
        assert result.text == "the agent looped on the search tool."

    async def test_concatenates_multiple_text_blocks(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=DEFAULT_API_URL,
            json={
                "content": [
                    {"type": "text", "text": "first block. "},
                    {"type": "tool_use", "name": "ignored"},
                    {"type": "text", "text": "second block."},
                ],
            },
        )
        client = ClaudeClient(api_key="sk-test")
        result = await client.summarize(system="x", user="y")
        assert result.text == "first block. second block."


# ---------------------------------------------------------------------------
# Trim helper
# ---------------------------------------------------------------------------


class TestTrim:
    def test_under_cap_passes_through(self):
        s, u = _trim_to_cap("hello", "world", cap=100)
        assert s == "hello"
        assert u == "world"

    def test_over_cap_trims_user_from_front(self):
        s, u = _trim_to_cap("sys", "x" * 100, cap=50)
        # System (3 chars) + remaining user must be 50.
        assert len(s) + len(u) == 50

    def test_oversized_system_alone_is_tail_trimmed(self):
        s, u = _trim_to_cap("x" * 200, "tail", cap=50)
        assert u == ""
        assert len(s) == 50


def test_prompt_hard_cap_is_pinned():
    # Documented limit. Shouldn't quietly drift.
    assert PROMPT_HARD_CAP_CHARS == 12_000
