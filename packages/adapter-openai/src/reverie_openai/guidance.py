"""Fetch user-supplied guidance from the Reverie backend.

After a run, the user can mark nodes in the 3D explorer (or via the CLI)
as ``avoid`` / ``focus`` / ``done`` / ``note``. Those annotations live in
Reverie's database keyed by ``agent_id``. On the next run, this module
fetches them and exposes the rendered prompt-prefix so the agent can see
the user's feedback.

Activation is opt-in via ``REVERIE_USE_GUIDANCE=1``. When unset (the
default), this module is dormant and adds zero overhead.

Public surface
--------------

- :func:`fetch_guidance` — synchronous best-effort GET. Never raises.
- :func:`apply_guidance_to_agent` — wraps an OpenAI Agents SDK ``Agent``
  by prepending the prompt-prefix to its ``instructions``.

Both functions degrade silently if the backend is unreachable, the env
var is unset, or no annotations exist for the agent.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("reverie_openai.guidance")


def _truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


def is_guidance_enabled() -> bool:
    """Whether the user has opted into next-run guidance for this process."""

    return _truthy(os.environ.get("REVERIE_USE_GUIDANCE"))


def fetch_guidance(
    *,
    backend_url: str | None = None,
    agent_id: str | None = None,
    tag: str | None = None,
    timeout_seconds: float = 1.5,
) -> str | None:
    """Best-effort GET ``/api/v1/agents/{agent_id}/guidance``.

    Returns the prompt-prefix string when guidance exists, ``None`` otherwise
    (no annotations, backend unreachable, env disabled, etc.). Never raises.

    Args:
        backend_url: Reverie backend root URL. Defaults to
            ``REVERIE_BACKEND_URL`` or ``http://127.0.0.1:8000``.
        agent_id: Agent identifier to look up. Defaults to
            ``REVERIE_AGENT_ID`` or ``"openai-agent"``.
        tag: Optional topic filter — only annotations with this tag (or no
            tag at all) are returned. Defaults to ``REVERIE_GUIDANCE_TAG``
            if unset.
        timeout_seconds: Per-request timeout. Kept short — guidance is a
            convenience, not a hard dependency.
    """

    if not is_guidance_enabled():
        return None

    base = backend_url or os.environ.get(
        "REVERIE_BACKEND_URL", "http://127.0.0.1:8000"
    )
    aid = agent_id or os.environ.get("REVERIE_AGENT_ID", "openai-agent")
    t = tag if tag is not None else os.environ.get("REVERIE_GUIDANCE_TAG")

    params: dict[str, Any] = {}
    if t:
        params["tag"] = t

    try:
        with httpx.Client(timeout=httpx.Timeout(timeout_seconds)) as client:
            resp = client.get(
                f"{base.rstrip('/')}/api/v1/agents/{aid}/guidance",
                params=params,
            )
        if resp.status_code != 200:
            logger.debug(
                "reverie guidance unavailable: HTTP %s", resp.status_code
            )
            return None
        body = resp.json()
    except Exception as exc:
        # Backend off, network glitch, malformed response — all fine. The
        # agent runs without guidance.
        logger.debug("reverie guidance fetch failed: %s", exc)
        return None

    prefix = body.get("promptPrefix") or body.get("prompt_prefix") or ""
    prefix = prefix.strip()
    return prefix or None


def apply_guidance_to_instructions(
    instructions: str | None,
    guidance: str | None,
) -> str | None:
    """Prepend guidance to an instruction string, with a clean separator.

    Returns ``instructions`` unchanged when ``guidance`` is empty/None.
    """

    if not guidance:
        return instructions
    if not instructions:
        return guidance
    return f"{guidance}\n\n---\n\n{instructions}"


def apply_guidance_to_agent(agent: Any, *, tag: str | None = None) -> str | None:
    """Mutate an OpenAI Agents SDK ``Agent`` in-place to include guidance.

    Returns the guidance string that was applied (or ``None`` if no
    guidance was applied for any reason). Useful in code:

    .. code-block:: python

        from agents import Agent
        from reverie_openai.guidance import apply_guidance_to_agent

        agent = Agent(name="research", instructions="...")
        applied = apply_guidance_to_agent(agent)
        if applied:
            print("agent steered by", applied.count("\\n"), "guidance lines")

    The function never raises. If ``agent`` doesn't have an
    ``instructions`` attribute, it's left untouched.
    """

    if not hasattr(agent, "instructions"):
        return None

    guidance = fetch_guidance(tag=tag)
    if not guidance:
        return None

    new_instructions = apply_guidance_to_instructions(
        getattr(agent, "instructions", None), guidance
    )
    try:
        agent.instructions = new_instructions
    except Exception:
        # Frozen dataclass / pydantic model? Give up gracefully — the agent
        # still runs without guidance.
        return None
    return guidance
