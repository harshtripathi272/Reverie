"""Adapter configuration.

Environment variables (all optional) override defaults. Tests construct
``AdapterConfig`` directly to avoid env-var leakage between cases.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
DEFAULT_AGENT_ID = "openai-agent"
DEFAULT_RUNTIME = "openai-agents"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AdapterConfig:
    """Adapter knobs. All fields have safe defaults."""

    backend_url: str = DEFAULT_BACKEND_URL
    agent_id: str = DEFAULT_AGENT_ID
    runtime: str = DEFAULT_RUNTIME

    # Bounded queue between SDK callbacks and the HTTP background loop.
    queue_size: int = 10_000
    # Max events per POST /events/batch.
    batch_size: int = 50
    # Maximum time the background loop waits to fill a batch before flushing.
    flush_interval_ms: int = 100
    # Per-request HTTP timeout. Short — agent must never hang because of us.
    request_timeout_seconds: float = 2.0

    # If True, the adapter is fully wired but emits nothing. Useful for tests.
    disabled: bool = False

    # Headers to send on every request (e.g. auth tokens, env labels).
    extra_headers: dict[str, str] = field(default_factory=dict)


def load_config() -> AdapterConfig:
    """Build a fresh :class:`AdapterConfig` from the current environment."""

    return AdapterConfig(
        backend_url=os.environ.get("REVERIE_BACKEND_URL", DEFAULT_BACKEND_URL),
        agent_id=os.environ.get("REVERIE_AGENT_ID", DEFAULT_AGENT_ID),
        runtime=os.environ.get("REVERIE_RUNTIME", DEFAULT_RUNTIME),
        queue_size=_env_int("REVERIE_QUEUE_SIZE", 10_000),
        batch_size=_env_int("REVERIE_BATCH_SIZE", 50),
        flush_interval_ms=_env_int("REVERIE_FLUSH_MS", 100),
        request_timeout_seconds=_env_float("REVERIE_TIMEOUT_S", 2.0),
        disabled=_env_bool("REVERIE_DISABLED", default=False),
    )
