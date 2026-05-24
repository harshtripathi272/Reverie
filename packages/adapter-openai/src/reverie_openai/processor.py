"""``TracingProcessor`` implementation that bridges the OpenAI Agents SDK
to the Reverie backend.

The SDK calls ``on_trace_*`` and ``on_span_*`` from sync code on whatever
thread is running the agent. This class is the only place that thread runs
our code, so we keep it short and offload everything else to the emitter.

Responsibilities
----------------

- **Run bookkeeping.** ``on_trace_start`` registers a Reverie run via the
  emitter; ``on_trace_end`` marks it completed/failed.
- **Tree depth tracking.** SDK spans carry ``parent_id`` but not ``depth``.
  We maintain a per-trace map from span_id to depth so each event can be
  located in the tree without re-traversing.
- **Translation.** Hands span/trace objects to :mod:`reverie_openai.mapper`
  for conversion to ``CognitiveEvent`` then queues the result.

This class never blocks, never raises out, and never imports anything from
the agent's runtime path.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from agents.tracing.processor_interface import TracingProcessor
from agents.tracing.spans import Span
from agents.tracing.traces import Trace

from reverie_openai.config import AdapterConfig
from reverie_openai.emitter import Emitter
from reverie_openai.mapper import (
    map_span_end,
    map_span_start,
    trace_run_id,
    trace_run_started_at,
    trace_session_id,
    trace_workflow_name,
)

logger = logging.getLogger("reverie_openai.processor")

_DEPTH_LIMIT = 256  # safety: prevent runaway recursion in malformed trees


class _TraceState:
    __slots__ = ("session_id", "agent_id", "run_id", "depths")

    def __init__(self, *, session_id: str, agent_id: str, run_id: str) -> None:
        self.session_id = session_id
        self.agent_id = agent_id
        self.run_id = run_id
        # span_id -> depth (0 = root span under the trace)
        self.depths: dict[str, int] = {}


class ReverieTracingProcessor(TracingProcessor):
    """Translate SDK trace/span events to Reverie CognitiveEvents."""

    def __init__(self, emitter: Emitter, config: AdapterConfig) -> None:
        self._emitter = emitter
        self._config = config
        # Indexed by SDK trace_id (NOT the Reverie run_id, which is a derived
        # UUID — the SDK gives us the SDK id and we look up state from that).
        self._traces: dict[str, _TraceState] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ trace

    def on_trace_start(self, trace: Trace) -> None:
        try:
            session_id = trace_session_id(trace)
            run_id = trace_run_id(trace)
            agent_id = self._config.agent_id

            state = _TraceState(
                session_id=session_id,
                agent_id=agent_id,
                run_id=run_id,
            )
            with self._lock:
                self._traces[trace.trace_id] = state

            payload = {
                "runId": run_id,
                "sessionId": session_id,
                "agentId": agent_id,
                "runtime": self._config.runtime,
                "startedAt": trace_run_started_at(trace),
                "goal": trace_workflow_name(trace),
            }
            self._emitter.create_run(payload)
        except Exception:
            logger.exception("reverie_openai.on_trace_start failed")

    def on_trace_end(self, trace: Trace) -> None:
        try:
            with self._lock:
                state = self._traces.pop(trace.trace_id, None)
            if state is None:
                return
            self._emitter.update_run(
                state.run_id,
                {
                    "status": "completed",
                    "completedAt": trace_run_started_at(trace),  # = now
                },
            )
        except Exception:
            logger.exception("reverie_openai.on_trace_end failed")

    # ------------------------------------------------------------------- span

    def _state_for(self, trace_id: str) -> _TraceState | None:
        with self._lock:
            return self._traces.get(trace_id)

    def _depth_for(self, span: Span[Any]) -> int:
        state = self._state_for(span.trace_id)
        if state is None:
            return 0
        parent = span.parent_id
        if parent is None:
            depth = 0
        else:
            depth = state.depths.get(parent, 0) + 1
        if depth > _DEPTH_LIMIT:
            depth = _DEPTH_LIMIT
        # Memoize so children of this span can read it directly.
        state.depths[span.span_id] = depth
        return depth

    def on_span_start(self, span: Span[Any]) -> None:
        try:
            state = self._state_for(span.trace_id)
            if state is None:
                # Span before trace? Skip — adapter cannot place this event.
                return

            depth = self._depth_for(span)
            event = map_span_start(
                span,
                session_id=state.session_id,
                agent_id=state.agent_id,
                depth=depth,
            )
            if event is not None:
                self._emitter.emit(event)
        except Exception:
            logger.exception("reverie_openai.on_span_start failed")

    def on_span_end(self, span: Span[Any]) -> None:
        try:
            state = self._state_for(span.trace_id)
            if state is None:
                return

            # Use the same depth assigned at start (not recomputed).
            depth = state.depths.get(span.span_id, 0)

            event = map_span_end(
                span,
                session_id=state.session_id,
                agent_id=state.agent_id,
                depth=depth,
            )
            if event is not None:
                self._emitter.emit(event)
        except Exception:
            logger.exception("reverie_openai.on_span_end failed")

    # --------------------------------------------------------------- shutdown

    def shutdown(self) -> None:
        try:
            self._emitter.shutdown()
        except Exception:
            logger.exception("reverie_openai.shutdown failed")

    def force_flush(self) -> None:
        try:
            self._emitter.flush()
        except Exception:
            logger.exception("reverie_openai.force_flush failed")
