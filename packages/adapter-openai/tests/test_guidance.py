"""Tests for the optional next-run guidance fetcher in the adapter."""

from __future__ import annotations

import httpx
import pytest

from reverie_openai.guidance import (
    apply_guidance_to_agent,
    apply_guidance_to_instructions,
    fetch_guidance,
    is_guidance_enabled,
)


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("REVERIE_USE_GUIDANCE", raising=False)
    assert is_guidance_enabled() is False
    assert fetch_guidance() is None


def test_enabled_via_env(monkeypatch):
    for value in ("1", "true", "yes", "on"):
        monkeypatch.setenv("REVERIE_USE_GUIDANCE", value)
        assert is_guidance_enabled() is True


def test_fetch_returns_prompt_prefix(monkeypatch):
    monkeypatch.setenv("REVERIE_USE_GUIDANCE", "1")
    monkeypatch.setenv("REVERIE_BACKEND_URL", "http://stub.local")
    monkeypatch.setenv("REVERIE_AGENT_ID", "research-bot")

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "agentId": "research-bot",
                "items": [{"kind": "avoid", "nodeId": "evt-1"}],
                "promptPrefix": "PRIOR RUN GUIDANCE FROM USER:\n  - avoid X",
                "markdown": "### Avoid\n- evt-1",
                "generatedAt": 1,
            },
        )

    transport = httpx.MockTransport(handler)
    OriginalClient = httpx.Client

    def patched_client(*args, **kwargs):
        # Inject the mock transport without recursing through the patched
        # ``httpx.Client`` symbol.
        kwargs["transport"] = transport
        return OriginalClient(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", patched_client)

    result = fetch_guidance()
    assert result is not None
    assert "PRIOR RUN GUIDANCE FROM USER" in result
    # The agent_id from the env must end up in the URL.
    assert "/api/v1/agents/research-bot/guidance" in captured["url"]


def test_fetch_handles_backend_offline(monkeypatch):
    monkeypatch.setenv("REVERIE_USE_GUIDANCE", "1")
    monkeypatch.setenv("REVERIE_BACKEND_URL", "http://stub.local")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("backend offline", request=request)

    transport = httpx.MockTransport(handler)
    OriginalClient = httpx.Client

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return OriginalClient(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", patched_client)

    # Must NOT raise; returns None.
    assert fetch_guidance() is None


def test_fetch_handles_non_200(monkeypatch):
    monkeypatch.setenv("REVERIE_USE_GUIDANCE", "1")
    monkeypatch.setenv("REVERIE_BACKEND_URL", "http://stub.local")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    transport = httpx.MockTransport(handler)
    OriginalClient = httpx.Client

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return OriginalClient(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", patched_client)

    assert fetch_guidance() is None


def test_apply_guidance_prepends_with_separator():
    out = apply_guidance_to_instructions("You are a research bot.", "AVOID X")
    assert out is not None
    assert out.startswith("AVOID X")
    assert "You are a research bot." in out
    assert "---" in out


def test_apply_guidance_passes_through_when_no_guidance():
    assert apply_guidance_to_instructions("X", None) == "X"
    assert apply_guidance_to_instructions("X", "") == "X"


def test_apply_guidance_to_empty_instructions():
    assert apply_guidance_to_instructions(None, "G") == "G"
    assert apply_guidance_to_instructions("", "G") == "G"


def test_apply_to_agent_mutates_instructions(monkeypatch):
    monkeypatch.setenv("REVERIE_USE_GUIDANCE", "1")
    monkeypatch.setenv("REVERIE_BACKEND_URL", "http://stub.local")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "agentId": "openai-agent",
                "items": [{"kind": "avoid", "nodeId": "evt-1"}],
                "promptPrefix": "AVOID DEAD ENDS",
                "markdown": "",
                "generatedAt": 1,
            },
        )

    transport = httpx.MockTransport(handler)
    OriginalClient = httpx.Client

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return OriginalClient(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", patched_client)

    class FakeAgent:
        def __init__(self) -> None:
            self.instructions = "Be a research assistant."

    agent = FakeAgent()
    applied = apply_guidance_to_agent(agent)
    assert applied is not None
    assert agent.instructions.startswith("AVOID DEAD ENDS")
    assert "Be a research assistant." in agent.instructions


def test_apply_to_agent_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("REVERIE_USE_GUIDANCE", raising=False)

    class FakeAgent:
        def __init__(self) -> None:
            self.instructions = "Stay you."

    agent = FakeAgent()
    assert apply_guidance_to_agent(agent) is None
    assert agent.instructions == "Stay you."


def test_apply_to_agent_noop_for_objects_without_instructions(monkeypatch):
    monkeypatch.setenv("REVERIE_USE_GUIDANCE", "1")

    class NoAttr:
        pass

    obj = NoAttr()
    # Must not raise — must return None — must not add the attribute.
    assert apply_guidance_to_agent(obj) is None
    assert not hasattr(obj, "instructions")
