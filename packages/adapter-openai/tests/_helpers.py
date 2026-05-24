"""Shared test helpers — non-fixture utilities used across modules.

Imported as ``from _helpers import ...`` thanks to the path-adjusting
``conftest.py`` in this directory (which adds tests dir to sys.path under
pytest's ``importlib`` mode).
"""

from __future__ import annotations

from typing import Any

from agents.tracing.processor_interface import TracingProcessor
from agents.tracing.span_data import (
    AgentSpanData,
    CustomSpanData,
    FunctionSpanData,
    GenerationSpanData,
    GuardrailSpanData,
    HandoffSpanData,
    ResponseSpanData,
)
from agents.tracing.spans import Span, SpanError, SpanImpl
from agents.tracing.traces import Trace, TraceImpl


class CapturingProcessor(TracingProcessor):
    """A processor that records every call but does nothing else."""

    def __init__(self) -> None:
        self.trace_starts: list[Trace] = []
        self.trace_ends: list[Trace] = []
        self.span_starts: list[Span[Any]] = []
        self.span_ends: list[Span[Any]] = []
        self.flushed = 0
        self.shutdowns = 0

    def on_trace_start(self, trace):
        self.trace_starts.append(trace)

    def on_trace_end(self, trace):
        self.trace_ends.append(trace)

    def on_span_start(self, span):
        self.span_starts.append(span)

    def on_span_end(self, span):
        self.span_ends.append(span)

    def shutdown(self):
        self.shutdowns += 1

    def force_flush(self):
        self.flushed += 1


def make_trace(
    *,
    name: str = "wf",
    trace_id: str = "trace_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    group_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    processor: TracingProcessor | None = None,
) -> TraceImpl:
    return TraceImpl(
        name=name,
        trace_id=trace_id,
        group_id=group_id,
        metadata=metadata,
        processor=processor or CapturingProcessor(),
    )


def make_span(
    span_data,
    *,
    trace_id: str = "trace_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    span_id: str = "span_000000000000000000000001",
    parent_id: str | None = None,
    started_at: str | None = "2025-01-01T12:00:00.000+00:00",
    ended_at: str | None = "2025-01-01T12:00:00.500+00:00",
    error: SpanError | None = None,
    processor: TracingProcessor | None = None,
) -> SpanImpl:
    span = SpanImpl(
        trace_id=trace_id,
        span_id=span_id,
        parent_id=parent_id,
        processor=processor or CapturingProcessor(),
        span_data=span_data,
        tracing_api_key=None,
    )
    span._started_at = started_at  # noqa: SLF001 — test-only access
    span._ended_at = ended_at  # noqa: SLF001
    if error is not None:
        span.set_error(error)
    return span


# Convenience builders for the most common span types.
def agent_span_data(name: str = "researcher") -> AgentSpanData:
    return AgentSpanData(name=name, handoffs=[], tools=[], output_type=None)


def function_span_data(
    name: str = "search_web",
    input: str | None = '{"query": "x"}',
    output: Any = None,
) -> FunctionSpanData:
    return FunctionSpanData(name=name, input=input, output=output)


def handoff_span_data(
    from_agent: str = "router", to_agent: str = "researcher"
) -> HandoffSpanData:
    return HandoffSpanData(from_agent=from_agent, to_agent=to_agent)


def generation_span_data(
    model: str = "gpt-4o-mini", tokens: int = 100
) -> GenerationSpanData:
    return GenerationSpanData(
        input=[{"role": "user", "content": "hi"}],
        output=[{"content": "hello!"}],
        model=model,
        model_config={"temperature": 0.7},
        usage={"total_tokens": tokens, "input_tokens": 60, "output_tokens": 40},
    )


def response_span_data() -> ResponseSpanData:
    return ResponseSpanData(response=None, input="hi", usage={"total_tokens": 50})


def guardrail_span_data(
    name: str = "pii_check", triggered: bool = False
) -> GuardrailSpanData:
    return GuardrailSpanData(name=name, triggered=triggered)


def custom_span_data(name: str = "db_query") -> CustomSpanData:
    return CustomSpanData(name=name, data={"table": "users"})
