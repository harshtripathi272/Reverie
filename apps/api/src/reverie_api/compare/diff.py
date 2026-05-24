"""Compute the structured diff between two aligned runs.

Produces a :class:`ComparisonDiff` with everything the SRS lists under the
"Comparison dimensions" table:

  - Trajectory divergence (the divergence point)
  - Token delta
  - Tool call diff
  - Memory diff (which retrievals returned different results)
  - Retry delta
  - Time delta
  - Failure root cause (handled by :mod:`fault_tree`, referenced here)
"""

from __future__ import annotations

from dataclasses import dataclass

from reverie_schema import CognitiveEvent

from reverie_api.compare.align import AlignmentResult


@dataclass(frozen=True)
class DivergencePoint:
    """The earliest place the two runs took different paths."""

    pair_index: int  # index into AlignmentResult.pairs
    a_event_id: str | None
    b_event_id: str | None
    reason: str


@dataclass(frozen=True)
class ComparisonDiff:
    """Structured outcome of comparing two runs."""

    run_a_id: str
    run_b_id: str
    alignment_score: float
    matched_count: int
    only_a_count: int
    only_b_count: int

    divergence: DivergencePoint | None

    token_delta: int  # b_tokens - a_tokens (positive = B used more)
    duration_delta_ms: int  # b_duration - a_duration

    extra_tools_in_b: list[str]
    missing_tools_in_b: list[str]

    retries_in_a: int
    retries_in_b: int

    failures_in_a: int
    failures_in_b: int


# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------


def compute_diff(
    *,
    run_a_id: str,
    run_b_id: str,
    events_a: list[CognitiveEvent],
    events_b: list[CognitiveEvent],
    alignment: AlignmentResult,
) -> ComparisonDiff:
    """Build the full comparison diff from an alignment + the raw event lists."""

    div = _find_divergence(alignment, events_a, events_b)

    tokens_a = sum(_token_cost(e) for e in events_a)
    tokens_b = sum(_token_cost(e) for e in events_b)

    duration_a = _run_duration_ms(events_a)
    duration_b = _run_duration_ms(events_b)

    tools_a = _tools_called(events_a)
    tools_b = _tools_called(events_b)
    extra_in_b = sorted(tools_b - tools_a)
    missing_in_b = sorted(tools_a - tools_b)

    retries_a = sum(1 for e in events_a if e.type == "retry.triggered")
    retries_b = sum(1 for e in events_b if e.type == "retry.triggered")

    failures_a = sum(1 for e in events_a if _is_failure(e))
    failures_b = sum(1 for e in events_b if _is_failure(e))

    return ComparisonDiff(
        run_a_id=run_a_id,
        run_b_id=run_b_id,
        alignment_score=alignment.score,
        matched_count=alignment.matched_count,
        only_a_count=alignment.only_a_count,
        only_b_count=alignment.only_b_count,
        divergence=div,
        token_delta=tokens_b - tokens_a,
        duration_delta_ms=duration_b - duration_a,
        extra_tools_in_b=extra_in_b,
        missing_tools_in_b=missing_in_b,
        retries_in_a=retries_a,
        retries_in_b=retries_b,
        failures_in_a=failures_a,
        failures_in_b=failures_b,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_divergence(
    alignment: AlignmentResult,
    events_a: list[CognitiveEvent],
    events_b: list[CognitiveEvent],
) -> DivergencePoint | None:
    """The first non-match (or low-similarity match) pair is the divergence
    point. If the runs are perfectly identical, returns None.

    A "divergence" is the earliest position where:
      - one run has an event the other doesn't (only_a / only_b), OR
      - both runs have events but with **different identity** (e.g. different
        tool names) — represented as a match with similarity < 1.0.
    """

    for i, pair in enumerate(alignment.pairs):
        if pair.kind == "match" and pair.similarity >= 1.0:
            continue
        a_id = (
            events_a[pair.a_index].id if pair.a_index is not None else None
        )
        b_id = (
            events_b[pair.b_index].id if pair.b_index is not None else None
        )
        if pair.kind == "only_a":
            reason = "event present in A but not B"
        elif pair.kind == "only_b":
            reason = "event present in B but not A"
        else:
            # Lower-similarity match: same kind, different identity.
            reason = (
                "matched event has different identity "
                f"(similarity={pair.similarity:.1f})"
            )
        return DivergencePoint(
            pair_index=i, a_event_id=a_id, b_event_id=b_id, reason=reason
        )
    return None


def _token_cost(event: CognitiveEvent) -> int:
    payload = event.payload
    kind = getattr(payload, "kind", None)
    if kind == "tool":
        v = getattr(payload, "token_cost", None)
        return int(v) if isinstance(v, int) else 0
    if kind == "reasoning":
        v = getattr(payload, "tokens_used", None)
        return int(v) if isinstance(v, int) else 0
    return 0


def _run_duration_ms(events: list[CognitiveEvent]) -> int:
    if not events:
        return 0
    return max(e.timestamp for e in events) - min(e.timestamp for e in events)


def _tools_called(events: list[CognitiveEvent]) -> set[str]:
    out: set[str] = set()
    for e in events:
        if e.type == "tool.called":
            kind = getattr(e.payload, "kind", None)
            if kind == "tool":
                name = getattr(e.payload, "tool_name", None)
                if name:
                    out.add(name)
    return out


def _is_failure(event: CognitiveEvent) -> bool:
    return event.type in {
        "goal.failed",
        "tool.failed",
        "validation.failed",
        "retry.exhausted",
    }
