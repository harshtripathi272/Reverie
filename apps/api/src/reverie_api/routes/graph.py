"""Graph intelligence endpoints (Phase 2).

Endpoints
---------

``GET /api/v1/runs/{run_id}/graph?level=N``
    Full :class:`GraphBundle`, optionally filtered to nodes at zoom level
    ``<= N``. Edges that reference filtered-out nodes are dropped.

``GET /api/v1/runs/{run_id}/anomalies``
    Flat list of (node_id, anomaly) pairs — one row per annotation. Cheaper
    to render than the whole graph when all you want is the issue list.

``GET /api/v1/runs/{run_id}/criticalpath``
    Just the ordered event ids on the critical path, plus a mini-summary.

These routes are read-only and idempotent. The engine handles caching.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from reverie_api.graph import (
    GraphBundle,
    GraphEdge,
    GraphEngine,
    GraphNode,
    GraphSummary,
    get_graph_engine,
)
from reverie_api.graph.types import MAX_ZOOM, MIN_ZOOM

router = APIRouter(prefix="/api/v1", tags=["graph"])


# ---------------------------------------------------------------------------
# /graph
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{run_id}/graph",
    response_model=GraphBundle,
    response_model_by_alias=True,
    summary="Full cognitive graph for a run, optionally filtered by zoom level",
)
async def get_graph(
    run_id: str,
    engine: GraphEngine = Depends(get_graph_engine),
    level: int | None = Query(
        default=None,
        ge=MIN_ZOOM,
        le=MAX_ZOOM,
        description="Filter: only include nodes whose zoomLevel <= level.",
    ),
) -> GraphBundle:
    bundle = await engine.build(run_id)
    if level is None:
        return bundle
    return _filter_by_zoom(bundle, level)


def _filter_by_zoom(bundle: GraphBundle, level: int) -> GraphBundle:
    """Return a copy of the bundle with only nodes (and matching edges) at
    or below the given zoom level."""

    keep: set[str] = {n.id for n in bundle.nodes if int(n.zoom_level) <= level}
    nodes = [n for n in bundle.nodes if n.id in keep]
    edges = [e for e in bundle.edges if e.source in keep and e.target in keep]

    # Trim cluster member lists too — clusters that empty out get dropped.
    clusters = []
    for c in bundle.clusters:
        members = [m for m in c.member_event_ids if m in keep]
        if not members:
            continue
        # Pydantic models are immutable enough that model_copy is cleanest.
        clusters.append(c.model_copy(update={"member_event_ids": members}))

    # Per-zoom summary on the filtered view.
    per_zoom: dict[str, int] = {"1": 0, "2": 0, "3": 0, "4": 0}
    for n in nodes:
        per_zoom[str(int(n.zoom_level))] += 1

    return GraphBundle(
        run_id=bundle.run_id,
        nodes=nodes,
        edges=edges,
        clusters=clusters,
        critical_path=[
            cid for cid in bundle.critical_path if cid in keep
        ],
        summary=GraphSummary(
            total_nodes=len(nodes),
            total_edges=len(edges),
            nodes_per_zoom=per_zoom,
            anomalies_by_kind=bundle.summary.anomalies_by_kind,
            critical_path_length=sum(
                1 for cid in bundle.critical_path if cid in keep
            ),
        ),
    )


# ---------------------------------------------------------------------------
# /anomalies
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{run_id}/anomalies",
    summary="All anomaly annotations for a run",
)
async def get_anomalies(
    run_id: str,
    engine: GraphEngine = Depends(get_graph_engine),
) -> list[dict[str, Any]]:
    bundle = await engine.build(run_id)
    out: list[dict[str, Any]] = []
    for n in bundle.nodes:
        for a in n.anomalies:
            out.append(
                {
                    "eventId": n.id,
                    "eventType": n.type,
                    "label": n.label,
                    "timestamp": n.timestamp,
                    "kind": a.kind,
                    "severity": a.severity,
                    "detail": a.detail,
                }
            )
    return out


# ---------------------------------------------------------------------------
# /criticalpath
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{run_id}/criticalpath",
    summary="Critical path through the run",
)
async def get_critical_path(
    run_id: str,
    engine: GraphEngine = Depends(get_graph_engine),
) -> dict[str, Any]:
    bundle = await engine.build(run_id)
    return {
        "runId": bundle.run_id,
        "length": bundle.summary.critical_path_length,
        "eventIds": bundle.critical_path,
    }
