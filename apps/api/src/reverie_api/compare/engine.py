"""DB-aware orchestrator for the comparative debugger.

Combines:

- Event fetching for both runs.
- Semantic alignment (Needleman-Wunsch).
- Structured diff computation.
- Fault tree construction (when the run failed).
- Optional AI narrative via :class:`SummaryService`.

A simple in-memory LRU caches by ``(run_a_id, run_b_id)``. A pair flips its
key on order swap, so ``compare(A, B)`` and ``compare(B, A)`` are different
cache rows — that's correct because the diff is asymmetric (token_delta is
``b - a``).
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass

from reverie_schema import CognitiveEvent

from reverie_api.ai import SummaryService
from reverie_api.compare.align import AlignmentResult, align_runs
from reverie_api.compare.diff import ComparisonDiff, compute_diff
from reverie_api.compare.fault_tree import FaultTree, build_fault_tree
from reverie_api.db import Database, RunNotFoundError


_FAILURE_TYPES = {"goal.failed", "tool.failed", "validation.failed", "retry.exhausted"}


@dataclass(frozen=True)
class CompareResult:
    """Full comparison output bundled together for callers."""

    diff: ComparisonDiff
    alignment: AlignmentResult
    fault_tree_a: FaultTree | None
    fault_tree_b: FaultTree | None
    narrative: str  # AI-generated, may be empty if unavailable
    narrative_status: str  # "ok" | "no_api_key" | "disabled" | "rate_limited" | "api_error"


class CompareEngine:
    """Build :class:`CompareResult` instances on demand. Cache by run-pair."""

    def __init__(
        self,
        db: Database,
        summary_service: SummaryService | None = None,
        *,
        lru_size: int = 16,
    ) -> None:
        self._db = db
        self._summary = summary_service
        self._lru: OrderedDict[tuple[str, str], CompareResult] = OrderedDict()
        self._lru_size = lru_size
        self._lock = asyncio.Lock()

    async def compare(
        self,
        run_a_id: str,
        run_b_id: str,
        *,
        with_narrative: bool = True,
    ) -> CompareResult:
        run_a = await self._db.get_run(run_a_id)
        if run_a is None:
            raise RunNotFoundError(run_a_id)
        run_b = await self._db.get_run(run_b_id)
        if run_b is None:
            raise RunNotFoundError(run_b_id)

        async with self._lock:
            cached = self._lru.get((run_a_id, run_b_id))
            if cached is not None:
                self._lru.move_to_end((run_a_id, run_b_id))
                # If the cached version was cached without narrative and the
                # caller now wants one, fall through to recompute. Otherwise
                # return immediately.
                if not with_narrative or cached.narrative_status != "skipped":
                    return cached

        events_a = await self._db.list_events_for_run(run_a_id)
        events_b = await self._db.list_events_for_run(run_b_id)

        alignment = align_runs(events_a, events_b)
        diff = compute_diff(
            run_a_id=run_a_id,
            run_b_id=run_b_id,
            events_a=events_a,
            events_b=events_b,
            alignment=alignment,
        )

        ft_a = _first_fault_tree(events_a)
        ft_b = _first_fault_tree(events_b)

        narrative = ""
        narrative_status = "skipped"
        if with_narrative and self._summary is not None:
            narrative_payload = _narrative_payload(diff, ft_a, ft_b)
            result = await self._summary.summarize_comparison(
                comparison_id=f"{run_a_id}:{run_b_id}",
                diff=narrative_payload,
            )
            narrative = result.text
            narrative_status = result.status

        compare_result = CompareResult(
            diff=diff,
            alignment=alignment,
            fault_tree_a=ft_a,
            fault_tree_b=ft_b,
            narrative=narrative,
            narrative_status=narrative_status,
        )

        async with self._lock:
            self._lru[(run_a_id, run_b_id)] = compare_result
            self._lru.move_to_end((run_a_id, run_b_id))
            while len(self._lru) > self._lru_size:
                self._lru.popitem(last=False)

        return compare_result

    async def invalidate(self, run_a_id: str, run_b_id: str) -> None:
        async with self._lock:
            self._lru.pop((run_a_id, run_b_id), None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _first_fault_tree(events: list[CognitiveEvent]) -> FaultTree | None:
    for evt in events:
        if evt.type in _FAILURE_TYPES:
            return build_fault_tree(failure_event=evt, events=events)
    return None


def _narrative_payload(
    diff: ComparisonDiff,
    ft_a: FaultTree | None,
    ft_b: FaultTree | None,
) -> dict:
    """Compact, prompt-friendly representation of the comparison."""

    return {
        "runA": diff.run_a_id,
        "runB": diff.run_b_id,
        "matchedCount": diff.matched_count,
        "onlyAcount": diff.only_a_count,
        "onlyBcount": diff.only_b_count,
        "tokenDelta": diff.token_delta,
        "durationDeltaMs": diff.duration_delta_ms,
        "extraToolsInB": diff.extra_tools_in_b,
        "missingToolsInB": diff.missing_tools_in_b,
        "retriesInA": diff.retries_in_a,
        "retriesInB": diff.retries_in_b,
        "failuresInA": diff.failures_in_a,
        "failuresInB": diff.failures_in_b,
        "divergence": (
            None
            if diff.divergence is None
            else {
                "aEventId": diff.divergence.a_event_id,
                "bEventId": diff.divergence.b_event_id,
                "reason": diff.divergence.reason,
            }
        ),
        "faultTreeA": (
            None if ft_a is None
            else {"chain": ft_a.chain_event_ids, "failureId": ft_a.failure_event_id}
        ),
        "faultTreeB": (
            None if ft_b is None
            else {"chain": ft_b.chain_event_ids, "failureId": ft_b.failure_event_id}
        ),
    }


# ---------------------------------------------------------------------------
# DI helpers
# ---------------------------------------------------------------------------

_engine_instance: CompareEngine | None = None


def set_compare_engine(engine: CompareEngine | None) -> None:
    global _engine_instance
    _engine_instance = engine


def get_compare_engine() -> CompareEngine:
    if _engine_instance is None:
        raise RuntimeError("CompareEngine has not been initialised")
    return _engine_instance
