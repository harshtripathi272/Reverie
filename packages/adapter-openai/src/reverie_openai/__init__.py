"""Reverie adapter for the OpenAI Agents SDK.

Public surface
--------------

- :func:`auto` — zero-config instrumentation. Call once at process start.
- :func:`shutdown` — flush and close the emitter (called atexit by default).
- :class:`AdapterConfig` — typed configuration loaded from env or kwargs.
- :class:`ReverieTracingProcessor` — the SDK ``TracingProcessor`` wrapper.
- :class:`Emitter` — background HTTP emitter (exposed for tests / DI).

Most users only need ``reverie_openai.auto()``.
"""

from reverie_openai.config import AdapterConfig, load_config
from reverie_openai.emitter import Emitter
from reverie_openai.processor import ReverieTracingProcessor
from reverie_openai.runtime import auto, shutdown

__all__ = [
    "AdapterConfig",
    "Emitter",
    "ReverieTracingProcessor",
    "auto",
    "load_config",
    "shutdown",
]

__version__ = "0.1.0"
