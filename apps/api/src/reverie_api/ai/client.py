"""Minimal Anthropic Messages API client.

We deliberately don't depend on the Anthropic SDK for two reasons:

1. **Tiny dependency footprint.** Reverie should ``pip install`` cleanly
   without pulling a SaaS-specific SDK that the server needs only sometimes.
2. **Graceful degradation.** The whole point of this module is that the
   server must *work fully* even when ``ANTHROPIC_API_KEY`` isn't set.
   Hard-depending on an SDK that requires the key at import time would
   break that.

So we speak the Messages API directly via ``httpx``. The interface is
documented here:
https://docs.anthropic.com/en/api/messages

The client returns :class:`SummaryResult` instances (not raw text) so the
cache layer can persist provenance — "this row came from the API at time T,
this other row is a 'no key configured' placeholder we should retry later",
etc.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

#: Pinned model id from the SRS. Bumping this is a deliberate decision.
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

DEFAULT_API_URL = "https://api.anthropic.com/v1/messages"

DEFAULT_MAX_TOKENS = 512

#: Hard cap on a single prompt's combined system + user content. Keeps
#: ingestion of 100k-event runs from accidentally producing megabyte prompts.
PROMPT_HARD_CAP_CHARS = 12_000


SummaryStatus = Literal["ok", "no_api_key", "rate_limited", "api_error", "disabled"]


@dataclass(frozen=True)
class SummaryResult:
    """Outcome of a single summarization request."""

    text: str
    status: SummaryStatus
    model: str
    #: Detail explaining a non-``ok`` status. Empty on success.
    detail: str = ""

    @property
    def is_ok(self) -> bool:
        return self.status == "ok"


class ClaudeClient:
    """Minimal Anthropic Messages client.

    Construct via :func:`get_claude_client` or directly. Most fields default
    to environment variables but every knob is overridable for tests.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_url: str = DEFAULT_API_URL,
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = 30.0,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        disabled: bool = False,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY")
        self._api_url = api_url
        self._model = model
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_tokens = max_tokens
        self._disabled = bool(disabled or os.environ.get("REVERIE_AI_DISABLED"))

    # ------------------------------------------------------------------ public

    @property
    def model(self) -> str:
        return self._model

    @property
    def is_configured(self) -> bool:
        """True iff a real API call would be attempted (vs returning a
        placeholder)."""

        return bool(self._api_key) and not self._disabled

    async def summarize(self, *, system: str, user: str) -> SummaryResult:
        """Issue a single Messages API call. Never raises.

        Trims oversized prompts so a runaway caller can't blow our token
        budget. The hard cap applies to the combined ``system + user``
        content; on overflow we keep the *tail* of ``user`` (the most
        recent events are typically more interesting than the prompt
        boilerplate at the top).
        """

        if self._disabled:
            return SummaryResult(
                text="",
                status="disabled",
                model=self._model,
                detail="ai summarization is disabled via REVERIE_AI_DISABLED",
            )
        if not self._api_key:
            return SummaryResult(
                text="",
                status="no_api_key",
                model=self._model,
                detail="ANTHROPIC_API_KEY is not set",
            )

        system, user = _trim_to_cap(system, user, PROMPT_HARD_CAP_CHARS)

        body = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self._api_url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            return SummaryResult(
                text="",
                status="api_error",
                model=self._model,
                detail=f"{type(exc).__name__}: {exc}",
            )

        if resp.status_code == 429:
            return SummaryResult(
                text="",
                status="rate_limited",
                model=self._model,
                detail=f"HTTP 429: {resp.text[:200]}",
            )
        if resp.status_code >= 400:
            return SummaryResult(
                text="",
                status="api_error",
                model=self._model,
                detail=f"HTTP {resp.status_code}: {resp.text[:200]}",
            )

        try:
            payload = resp.json()
            text = _extract_text(payload)
        except Exception as exc:  # pragma: no cover — defensive
            return SummaryResult(
                text="",
                status="api_error",
                model=self._model,
                detail=f"could not parse response: {exc!r}",
            )

        return SummaryResult(text=text, status="ok", model=self._model)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_text(payload: dict) -> str:
    """Pull the assistant text from a Messages API response.

    The wire shape is ``{"content": [{"type": "text", "text": "..."}, ...]}``.
    We concatenate all text blocks (rare to have more than one).
    """

    parts: list[str] = []
    for block in payload.get("content", []) or []:
        if isinstance(block, dict) and block.get("type") == "text":
            t = block.get("text", "")
            if isinstance(t, str):
                parts.append(t)
    return "".join(parts).strip()


def _trim_to_cap(system: str, user: str, cap: int) -> tuple[str, str]:
    """If ``len(system) + len(user) > cap``, trim ``user`` from the front."""

    over = (len(system) + len(user)) - cap
    if over <= 0:
        return system, user
    if over >= len(user):
        # System alone exceeds the cap. Trim it instead.
        return system[-cap:], ""
    return system, user[over:]


# ---------------------------------------------------------------------------
# DI helpers
# ---------------------------------------------------------------------------

_client_instance: ClaudeClient | None = None
_lock = asyncio.Lock()  # not strictly needed today but cheap insurance.


def set_claude_client(client: ClaudeClient | None) -> None:
    global _client_instance
    _client_instance = client


def get_claude_client() -> ClaudeClient:
    """Return the singleton client. Auto-constructs a default on first use."""

    global _client_instance
    if _client_instance is None:
        _client_instance = ClaudeClient()
    return _client_instance
