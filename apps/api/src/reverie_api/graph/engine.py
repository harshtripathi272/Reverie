"""Graph engine — DB-aware front-end for graph construction.

Builds a :class:`GraphBundle` for a run by:

1. Fetching events from the DB (timestamp + ingest_seq order).
2. Calling :func:`build_nodes_and_edges` for the DAG skeleton.
3. Running anomaly detectors and stamping each node.
4. Computing the critical path back from the run's first failure (or its
   most-token-consuming leaf if the run succeeded).
5. Grouping nodes into clusters keyed on top-level goals.

A simple per-run LRU caches the latest bundle so repeated zoom-level reads
don't re-walk the event log.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict

from reverie_api.db import Database, RunNotFoundError
from reverie_api.graph.anomalies import annotate_anomalies
from reverie_api.graph.build import build_nodes_and_edges
from reverie_api.graph.clusters import build_clusters
from reverie_api.graph.critical_path import compute_critical_path
from reverie_api.graph.types import (
    GraphBundle,
    GraphSummary,
)


class GraphEngine:
    """Build :class:`GraphBundle` instances on demand. Cache by run id."""

    def __init__(self, db: Database, *, lru_size: int = 16) -> None:
        self._db = db
        self._lru: OrderedDict[str, tuple[int, GraphBundle]] = OrderedDict()
        self._lru_size = lru_size
        self._lock = asyncio.Lock()

    async def build(self, run_id: str) -> GraphBundle:
        """Return a fully-annotated graph bundle for ``run_id``.

        Cached by ``(run_id, totalEvents)`` so repeated calls with no new
        events return the same bundle in O(1).
        """

        run = await self._db.get_run(run_id)
        if run is None:
            raise RunNotFoundError(run_id)

        async with self._lock:
            cached = self._lru.get(run_id)
            if cached is not None and cached[0] == run.total_events:
                self._lru.move_to_end(run_id)
                return cached[1]

        events = await self._db.list_events_for_run(run_id)
        nodes, edges = build_nodes_and_edges(events)

        # Stamp anomalies onto nodes.
        annotate_anomalies(nodes, events)

        # Compute critical path and mark its nodes/edges.
        critical_ids = compute_critical_path(nodes, edges, events)
        critical_set = set(critical_ids)
        for n in nodes:
            if n.id in critical_set:
                n.on_critical_path = True
        for e in edges:
            if e.source in critical_set and e.target in critical_set:
                e.on_critical_path = True

        # Build clusters and back-link nodes to their cluster.
        clusters = build_clusters(nodes, edges)
        cluster_by_event: dict[str, str] = {}
        for c in clusters:
            for eid in c.member_event_ids:
                cluster_by_event[eid] = c.id
        # Mark cluster refs on nodes.
        from reverie_api.graph.types import ClusterRef

        for n in nodes:
            cid = cluster_by_event.get(n.id)
            if cid is not None:
                role = "root"
                # Use the first member as the cluster's root unless it's an
                # explicit root_event_id.
                for c in clusters:
                    if c.id == cid and c.root_event_id == n.id:
                        role = "root"
                        break
                else:
                    role = "member"
                n.cluster = ClusterRef(cluster_id=cid, role=role)

        # Per-zoom counts.
        per_zoom = {"1": 0, "2": 0, "3": 0, "4": 0}
        for n in nodes:
            per_zoom[str(int(n.zoom_level))] += 1

        # Anomalies-by-kind summary.
        anomalies_by_kind: dict[str, int] = {}
        for n in nodes:
            for a in n.anomalies:
                anomalies_by_kind[a.kind] = anomalies_by_kind.get(a.kind, 0) + 1

        bundle = GraphBundle(
            run_id=run_id,
            nodes=nodes,
            edges=edges,
            clusters=clusters,
            critical_path=critical_ids,
            summary=GraphSummary(
                total_nodes=len(nodes),
                total_edges=len(edges),
                nodes_per_zoom=per_zoom,
                anomalies_by_kind=anomalies_by_kind,
                critical_path_length=len(critical_ids),
            ),
        )

        async with self._lock:
            self._lru[run_id] = (run.total_events, bundle)
            self._lru.move_to_end(run_id)
            while len(self._lru) > self._lru_size:
                self._lru.popitem(last=False)

        return bundle

    async def invalidate_run(self, run_id: str) -> None:
        async with self._lock:
            self._lru.pop(run_id, None)


# DI helpers (mirror snapshot.engine and db.connection).
_engine_instance: GraphEngine | None = None


def set_graph_engine(engine: GraphEngine | None) -> None:
    global _engine_instance
    _engine_instance = engine


def get_graph_engine() -> GraphEngine:
    if _engine_instance is None:
        raise RuntimeError("GraphEngine has not been initialised")
    return _engine_instance


__all__ = ["GraphEngine", "get_graph_engine", "set_graph_engine"]
