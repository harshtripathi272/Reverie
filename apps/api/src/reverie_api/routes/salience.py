"""Phase 3 routes — salience-scored graph + AI cluster summaries."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from reverie_api.ai import SummaryService, get_summary_service
from reverie_api.graph import GraphBundle, GraphEngine, get_graph_engine
from reverie_api.graph.types import MAX_ZOOM, MIN_ZOOM
from reverie_api.routes.graph import _filter_by_zoom  # reuse the level filter
from reverie_api.salience import (
    SALIENCE_NOISE_THRESHOLD,
    score_salience,
)

router = APIRouter(prefix="/api/v1", tags=["salience", "ai"])


# ---------------------------------------------------------------------------
# /salience  — scored graph
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{run_id}/salience",
    response_model=GraphBundle,
    response_model_by_alias=True,
    summary="Salience-scored cognitive graph for a run",
)
async def get_salience(
    run_id: str,
    engine: GraphEngine = Depends(get_graph_engine),
    level: int | None = Query(default=None, ge=MIN_ZOOM, le=MAX_ZOOM),
    hide_noise: bool = Query(
        default=False,
        description=(
            "If true, drop nodes whose salience falls below "
            f"{SALIENCE_NOISE_THRESHOLD}."
        ),
    ),
) -> GraphBundle:
    bundle = await engine.build(run_id)
    # Score in place. The graph engine's LRU caches the bundle, so two
    # /salience calls produce two scoring passes — but the scorer is cheap
    # and the result of one pass equals another (idempotent).
    score_salience(bundle)
    if level is not None:
        bundle = _filter_by_zoom(bundle, level)
    if hide_noise:
        bundle = _filter_by_salience(bundle, SALIENCE_NOISE_THRESHOLD)
    return bundle


def _filter_by_salience(bundle: GraphBundle, threshold: float) -> GraphBundle:
    """Drop nodes with salience strictly below ``threshold`` and any edges
    that reference them."""

    keep: set[str] = {
        n.id for n in bundle.nodes
        if n.salience is not None and n.salience >= threshold
    }
    nodes = [n for n in bundle.nodes if n.id in keep]
    edges = [e for e in bundle.edges if e.source in keep and e.target in keep]
    clusters = []
    for c in bundle.clusters:
        members = [m for m in c.member_event_ids if m in keep]
        if not members:
            continue
        clusters.append(c.model_copy(update={"member_event_ids": members}))
    per_zoom: dict[str, int] = {"1": 0, "2": 0, "3": 0, "4": 0}
    for n in nodes:
        per_zoom[str(int(n.zoom_level))] += 1
    from reverie_api.graph.types import GraphSummary

    return bundle.model_copy(
        update={
            "nodes": nodes,
            "edges": edges,
            "clusters": clusters,
            "critical_path": [cid for cid in bundle.critical_path if cid in keep],
            "summary": GraphSummary(
                total_nodes=len(nodes),
                total_edges=len(edges),
                nodes_per_zoom=per_zoom,
                anomalies_by_kind=bundle.summary.anomalies_by_kind,
                critical_path_length=sum(
                    1 for cid in bundle.critical_path if cid in keep
                ),
            ),
        }
    )


# ---------------------------------------------------------------------------
# Cluster AI summary
# ---------------------------------------------------------------------------


@router.post(
    "/runs/{run_id}/clusters/{cluster_id}/summary",
    summary="Get an AI summary for a graph cluster (cached if already produced)",
)
async def get_cluster_summary(
    run_id: str,
    cluster_id: str,
    engine: GraphEngine = Depends(get_graph_engine),
    service: SummaryService = Depends(get_summary_service),
    refresh: bool = Query(default=False),
) -> dict[str, Any]:
    bundle = await engine.build(run_id)

    cluster = next((c for c in bundle.clusters if c.id == cluster_id), None)
    if cluster is None:
        raise HTTPException(status_code=404, detail="cluster not found in this run")

    # Pull the events for this cluster's member nodes from the graph nodes
    # (we already have label + payload-derived hints in build._label, but for
    # a richer summary we need real event payloads). Re-fetch from the DB.
    member_ids = set(cluster.member_event_ids)
    node_subset = [n for n in bundle.nodes if n.id in member_ids]
    # The engine doesn't carry payloads on nodes — fall back to the full
    # event list and project.
    from reverie_api.db import get_database

    db = get_database()
    full_events = await db.list_events_for_run(run_id)
    member_events = [
        e.model_dump(by_alias=True) for e in full_events if e.id in member_ids
    ]

    result = await service.summarize_cluster(
        cluster_id=f"{run_id}:{cluster_id}",
        events=member_events,
        force_refresh=refresh,
    )
    return {
        "runId": run_id,
        "clusterId": cluster_id,
        "memberCount": len(node_subset),
        "summary": result.text,
        "status": result.status,
        "model": result.model,
        "detail": result.detail,
    }
