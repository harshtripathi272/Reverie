"""Translate OpenAI Agents SDK ``Span`` / ``Trace`` objects into Reverie
``CognitiveEvent`` instances.

This module is one half of the moat — the OpenAI runtime's semantics live on
one side, the universal CognitiveEvent schema on the other, and this
translation is the contract.

Topology model
--------------

Each SDK span produces:

- on ``on_span_start``: at most one ``CognitiveEvent`` with ``id =
  to_uuid(span_id)`` and ``parent_id = to_uuid(span.parent_id)`` (or None for
  root-of-trace spans).
- on ``on_span_end``: at most one ``CognitiveEvent`` with ``id =
  to_end_uuid(span_id)`` and the *same* ``parent_id`` as the start event.

Both events sit at the same position in the tree. They are siblings under the
parent, ordered by timestamp. This matches the SDK's span tree exactly.

Design rules
------------

1. **The schema is frozen.** Anything we don't have a payload mapping for goes
   into a :class:`GenericPayload` so downstream consumers see *something*.
2. **Defensive attribute access.** SDK shapes drift across versions. Use
   ``getattr(..., default)`` for everything we don't strictly require.
3. **No I/O, no side effects.** Pure translation. Errors propagate to the
   caller (the processor) which handles them.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from agents.tracing.span_data import (
    AgentSpanData,
    CustomSpanData,
    FunctionSpanData,
    GenerationSpanData,
    GuardrailSpanData,
    HandoffSpanData,
    MCPListToolsSpanData,
    ResponseSpanData,
)
from agents.tracing.spans import Span
from agents.tracing.traces import Trace
from reverie_schema import (
    CognitiveEvent,
    GenericPayload,
    GoalPayload,
    ReasoningPayload,
    SubagentPayload,
    ToolPayload,
    ValidationPayload,
)

from reverie_openai.idmap import to_end_uuid, to_uuid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_ms() -> int:
    return int(time.time() * 1000)


def _iso_to_ms(value: str | None) -> int | None:
    """Parse the SDK's ISO-8601 timestamp strings to unix milliseconds.

    The SDK uses naive UTC ISO strings (e.g. ``"2025-01-01T12:00:00.123Z"``).
    We accept anything ``datetime.fromisoformat`` understands plus the trailing
    ``Z`` shorthand for UTC.
    """

    if value is None:
        return None
    try:
        s = value.replace("Z", "+00:00") if value.endswith("Z") else value
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _duration_ms(span: Span[Any]) -> float | None:
    started = _iso_to_ms(span.started_at)
    ended = _iso_to_ms(span.ended_at)
    if started is None or ended is None:
        return None
    return float(max(0, ended - started))


def _safe_str(value: Any, *, max_len: int = 8192) -> str:
    """Coerce ``value`` to a printable string capped at ``max_len`` chars."""

    if value is None:
        return ""
    s = value if isinstance(value, str) else repr(value)
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s


def _safe_dict(value: Any) -> dict[str, Any]:
    """Best-effort conversion of arbitrary SDK input/output to a dict."""

    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    return {"value": _safe_str(value)}


def _generation_summary(data: GenerationSpanData) -> str | None:
    """Extract a human-readable one-liner from a generation span."""

    out = data.output
    if not out:
        return None
    try:
        first = out[0]
    except (IndexError, TypeError):
        return None
    if isinstance(first, dict):
        for key in ("content", "text", "output_text"):
            v = first.get(key)
            if isinstance(v, str) and v:
                return _safe_str(v, max_len=2000)
    return None


def _generation_tokens(usage: dict[str, Any] | None) -> int | None:
    if not usage:
        return None
    total = usage.get("total_tokens")
    if isinstance(total, int):
        return total
    inp = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
    out = usage.get("output_tokens") or usage.get("completion_tokens") or 0
    if isinstance(inp, int) and isinstance(out, int):
        s = inp + out
        return s if s > 0 else None
    return None


def _parent_uuid(span: Span[Any]) -> str | None:
    pid = span.parent_id
    return to_uuid(pid) if pid else None


# ---------------------------------------------------------------------------
# Run lifecycle helpers
# ---------------------------------------------------------------------------


def trace_run_started_at(trace: Trace) -> int:
    """Return a `started_at` timestamp for a trace.

    The SDK's :class:`Trace` has no started_at field; we use wall-clock now at
    the moment ``on_trace_start`` fires.
    """

    del trace  # unused — future-proofs us if SDK adds a timestamp
    return _now_ms()


def trace_workflow_name(trace: Trace) -> str:
    return _safe_str(trace.name) or "agent-workflow"


def trace_session_id(trace: Trace) -> str:
    """Pick a session id for the run.

    Convention:
      - If the user passed ``trace(group_id=...)`` use that.
      - Otherwise fall back to the trace id itself.
    """

    group_id = getattr(trace, "group_id", None)
    if isinstance(group_id, str) and group_id:
        return group_id
    return trace.trace_id


def trace_run_id(trace: Trace) -> str:
    """Reverie run id for a trace (UUID-shaped projection of trace_id)."""

    return to_uuid(trace.trace_id)


# ---------------------------------------------------------------------------
# Span → CognitiveEvent
# ---------------------------------------------------------------------------


def _common_kwargs(
    span: Span[Any],
    *,
    session_id: str,
    agent_id: str,
    depth: int,
    event_id: str,
    timestamp_ms: int,
    duration_ms: float | None,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "run_id": to_uuid(span.trace_id),
        "session_id": session_id,
        "agent_id": agent_id,
        "parent_id": _parent_uuid(span),
        "depth": depth,
        "timestamp": timestamp_ms,
        "duration_ms": duration_ms,
    }


def map_span_start(
    span: Span[Any],
    *,
    session_id: str,
    agent_id: str,
    depth: int,
) -> CognitiveEvent | None:
    """Translate ``on_span_start`` to a CognitiveEvent (or None to skip).

    Span types that only carry meaning on completion (generations, responses,
    guardrails) return ``None``; their data is emitted from
    :func:`map_span_end` instead.
    """

    data = span.span_data
    common = _common_kwargs(
        span,
        session_id=session_id,
        agent_id=agent_id,
        depth=depth,
        event_id=to_uuid(span.span_id),
        timestamp_ms=_iso_to_ms(span.started_at) or _now_ms(),
        duration_ms=None,
    )

    if isinstance(data, AgentSpanData):
        return CognitiveEvent(
            type="goal.created",
            payload=GoalPayload(
                intent=_safe_str(data.name),
                priority="high",
                context="",
            ),
            **common,
        )

    if isinstance(data, FunctionSpanData):
        return CognitiveEvent(
            type="tool.called",
            payload=ToolPayload(
                tool_name=_safe_str(data.name) or "unknown",
                args=_safe_dict(data.input),
                result=None,
                latency_ms=0.0,
                token_cost=None,
                success=True,
                error_message=None,
            ),
            **common,
        )

    if isinstance(data, HandoffSpanData):
        from_agent = _safe_str(data.from_agent) or "unknown"
        to_agent = _safe_str(data.to_agent) or "unknown"
        return CognitiveEvent(
            type="subagent.spawned",
            payload=SubagentPayload(
                agent_type=to_agent,
                task=f"handoff from {from_agent} to {to_agent}",
                delegated_goal_id=_parent_uuid(span),
                child_run_id=None,
            ),
            **common,
        )

    # Span types that are interesting only on completion.
    if isinstance(data, (GenerationSpanData, ResponseSpanData, GuardrailSpanData)):
        return None

    # Custom / mcp_tools / task / turn / speech / transcription — preserve
    # observability for forward-compat without claiming a known cognitive
    # primitive.
    if isinstance(data, (CustomSpanData, MCPListToolsSpanData)):
        return CognitiveEvent(
            type="planner.updated",
            payload=GenericPayload(
                data={
                    "stage": "start",
                    "sdk_span_type": data.type,
                    "details": data.export() if hasattr(data, "export") else {},
                }
            ),
            **common,
        )

    # Unknown span type — emit a placeholder rather than swallow.
    return CognitiveEvent(
        type="planner.updated",
        payload=GenericPayload(
            data={
                "stage": "start",
                "sdk_span_type": getattr(data, "type", "unknown"),
            }
        ),
        **common,
    )


def map_span_end(
    span: Span[Any],
    *,
    session_id: str,
    agent_id: str,
    depth: int,
) -> CognitiveEvent | None:
    """Translate ``on_span_end`` to a CognitiveEvent (or None)."""

    data = span.span_data
    error = span.error  # SpanError TypedDict | None
    duration_ms = _duration_ms(span)
    common = _common_kwargs(
        span,
        session_id=session_id,
        agent_id=agent_id,
        depth=depth,
        event_id=to_end_uuid(span.span_id),
        timestamp_ms=_iso_to_ms(span.ended_at) or _now_ms(),
        duration_ms=duration_ms,
    )

    if isinstance(data, AgentSpanData):
        is_failure = error is not None
        return CognitiveEvent(
            type="goal.failed" if is_failure else "goal.completed",
            payload=GoalPayload(
                intent=_safe_str(data.name),
                priority="high",
                context=_safe_str(error.get("message")) if error else "",
            ),
            **common,
        )

    if isinstance(data, FunctionSpanData):
        is_failure = error is not None
        return CognitiveEvent(
            type="tool.failed" if is_failure else "tool.returned",
            payload=ToolPayload(
                tool_name=_safe_str(data.name) or "unknown",
                args=_safe_dict(data.input),
                result=_safe_str(data.output) if data.output is not None else None,
                latency_ms=duration_ms or 0.0,
                token_cost=None,
                success=not is_failure,
                error_message=_safe_str(error.get("message")) if is_failure else None,
            ),
            **common,
        )

    if isinstance(data, HandoffSpanData):
        return CognitiveEvent(
            type="subagent.completed",
            payload=SubagentPayload(
                agent_type=_safe_str(data.to_agent) or "unknown",
                task=f"handoff: {_safe_str(data.from_agent)} → {_safe_str(data.to_agent)}",
                delegated_goal_id=None,
                child_run_id=None,
            ),
            **common,
        )

    if isinstance(data, (GenerationSpanData, ResponseSpanData)):
        usage = getattr(data, "usage", None)
        model_id = _safe_str(getattr(data, "model", None)) or "unknown"
        summary = _generation_summary(data) if isinstance(data, GenerationSpanData) else None
        return CognitiveEvent(
            type="reasoning.extracted",
            payload=ReasoningPayload(
                raw_text=None,
                summary=summary,
                model_id=model_id,
                tokens_used=_generation_tokens(usage),
            ),
            **common,
        )

    if isinstance(data, GuardrailSpanData):
        triggered = bool(getattr(data, "triggered", False))
        return CognitiveEvent(
            type="validation.failed" if triggered else "validation.passed",
            payload=ValidationPayload(
                check_name=_safe_str(data.name) or "guardrail",
                passed=not triggered,
                severity="error" if triggered else "info",
                details=_safe_str(error.get("message")) if error else "",
            ),
            **common,
        )

    if isinstance(data, (CustomSpanData, MCPListToolsSpanData)):
        return CognitiveEvent(
            type="planner.updated",
            payload=GenericPayload(
                data={
                    "stage": "end",
                    "sdk_span_type": data.type,
                    "details": data.export() if hasattr(data, "export") else {},
                    "error": dict(error) if error else None,
                }
            ),
            **common,
        )

    return CognitiveEvent(
        type="planner.updated",
        payload=GenericPayload(
            data={
                "stage": "end",
                "sdk_span_type": getattr(data, "type", "unknown"),
                "error": dict(error) if error else None,
            }
        ),
        **common,
    )
