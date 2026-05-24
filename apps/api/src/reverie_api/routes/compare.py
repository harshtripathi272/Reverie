"""Phase 4 routes — comparative debugger."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from reverie_api.compare import CompareEngine, get_compare_engine

router = APIRouter(prefix="/api/v1", tags=["compare"])


@router.post(
    "/compare",
    summary="Compare two runs and return diff + alignment + (optional) AI narrative",
)
async def compare_runs(
    body: dict,
    engine: CompareEngine = Depends(get_compare_engine),
    with_narrative: bool = Query(default=True),
) -> dict[str, Any]:
    """Build a full comparison report for two runs.

    Body shape:
        ``{"runAId": "...", "runBId": "..."}``

    Response shape (camelCase):
        ``{"diff": {...}, "alignment": {...}, "faultTreeA": {...}|null,
           "faultTreeB": {...}|null, "narrative": "...", "narrativeStatus": "ok"|...}``
    """

    run_a_id = body.get("runAId") or body.get("runIdA")
    run_b_id = body.get("runBId") or body.get("runIdB")
    if not run_a_id or not run_b_id:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail="runAId and runBId are required",
        )

    result = await engine.compare(run_a_id, run_b_id, with_narrative=with_narrative)
    return _result_to_wire(result)


def _result_to_wire(result) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    diff = result.diff
    return {
        "diff": {
            "runAId": diff.run_a_id,
            "runBId": diff.run_b_id,
            "alignmentScore": diff.alignment_score,
            "matchedCount": diff.matched_count,
            "onlyACount": diff.only_a_count,
            "onlyBCount": diff.only_b_count,
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
                    "pairIndex": diff.divergence.pair_index,
                    "aEventId": diff.divergence.a_event_id,
                    "bEventId": diff.divergence.b_event_id,
                    "reason": diff.divergence.reason,
                }
            ),
        },
        "alignment": {
            "score": result.alignment.score,
            "matchedCount": result.alignment.matched_count,
            "onlyACount": result.alignment.only_a_count,
            "onlyBCount": result.alignment.only_b_count,
            "pairs": [
                {
                    "kind": p.kind,
                    "aIndex": p.a_index,
                    "bIndex": p.b_index,
                    "similarity": p.similarity,
                }
                for p in result.alignment.pairs
            ],
        },
        "faultTreeA": (
            None
            if result.fault_tree_a is None
            else {
                "failureEventId": result.fault_tree_a.failure_event_id,
                "chainEventIds": result.fault_tree_a.chain_event_ids,
                "rootEventId": result.fault_tree_a.root_event_id,
            }
        ),
        "faultTreeB": (
            None
            if result.fault_tree_b is None
            else {
                "failureEventId": result.fault_tree_b.failure_event_id,
                "chainEventIds": result.fault_tree_b.chain_event_ids,
                "rootEventId": result.fault_tree_b.root_event_id,
            }
        ),
        "narrative": result.narrative,
        "narrativeStatus": result.narrative_status,
    }
