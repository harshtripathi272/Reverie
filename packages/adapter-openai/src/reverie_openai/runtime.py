"""Public entry points: :func:`auto` and :func:`shutdown`.

``auto()`` is idempotent: calling it more than once registers the processor
exactly once. The atexit hook is installed on first call so shutdowns flush
the queue cleanly even on uncaught exceptions.
"""

from __future__ import annotations

import atexit
import logging
import threading
from typing import Any

from agents.tracing import add_trace_processor

from reverie_openai.config import AdapterConfig, load_config
from reverie_openai.emitter import Emitter
from reverie_openai.processor import ReverieTracingProcessor

logger = logging.getLogger("reverie_openai")

_lock = threading.Lock()
_state: dict[str, Any] = {
    "installed": False,
    "emitter": None,
    "processor": None,
}


def auto(config: AdapterConfig | None = None) -> ReverieTracingProcessor:
    """Install Reverie instrumentation on the OpenAI Agents SDK.

    Idempotent. Subsequent calls return the existing processor.

    Args:
        config: optional :class:`AdapterConfig`. When ``None`` (the default),
            the configuration is loaded from environment variables.

    Returns:
        The installed :class:`ReverieTracingProcessor`.
    """

    with _lock:
        if _state["installed"]:
            return _state["processor"]

        cfg = config or load_config()
        emitter = Emitter(cfg)
        emitter.start()
        processor = ReverieTracingProcessor(emitter, cfg)

        add_trace_processor(processor)

        _state["emitter"] = emitter
        _state["processor"] = processor
        _state["installed"] = True

        atexit.register(_atexit_shutdown)

        if cfg.disabled:
            logger.info("reverie_openai installed in DISABLED mode")
        else:
            logger.info(
                "reverie_openai instrumented. Streaming to %s", cfg.backend_url
            )

        return processor


def shutdown(timeout: float = 5.0) -> None:
    """Flush queued events and stop the background emitter.

    Idempotent. Called automatically on interpreter exit.
    """

    with _lock:
        emitter: Emitter | None = _state.get("emitter")
        if emitter is None:
            return
        # Leave processor / installed flag in place — the SDK's processor
        # registry doesn't have a clean way to deregister, and a stopped
        # emitter is a no-op anyway.
    try:
        emitter.shutdown(timeout=timeout)
    except Exception:
        logger.exception("reverie_openai.shutdown failed")


def _atexit_shutdown() -> None:
    # Short timeout — exit shouldn't hang on a slow backend.
    try:
        shutdown(timeout=2.0)
    except Exception:
        pass
