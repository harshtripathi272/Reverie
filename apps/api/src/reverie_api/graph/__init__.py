"""Graph intelligence — DAG construction, anomaly detection, semantic zoom.

Public surface:

- :class:`GraphEngine` — DB-aware front-end; ``await engine.build(run_id)``.
- :class:`GraphBundle` — the on-the-wire shape of a fully-annotated graph.
- Pure helpers (:mod:`build`, :mod:`zoom`, :mod:`anomalies`, :mod:`critical_path`,
  :mod:`clusters`) for unit testing the pipeline without a database.
"""

from reverie_api.graph.engine import GraphEngine, get_graph_engine, set_graph_engine
from reverie_api.graph.types import (
    AnomalyAnnotation,
    AnomalyKind,
    ClusterRef,
    GraphBundle,
    GraphCluster,
    GraphEdge,
    GraphNode,
    GraphSummary,
    ZoomLevel,
)

__all__ = [
    "AnomalyAnnotation",
    "AnomalyKind",
    "ClusterRef",
    "GraphBundle",
    "GraphCluster",
    "GraphEdge",
    "GraphEngine",
    "GraphNode",
    "GraphSummary",
    "ZoomLevel",
    "get_graph_engine",
    "set_graph_engine",
]
