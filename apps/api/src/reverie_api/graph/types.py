"""Wire types for the graph intelligence layer.

Design rules
------------

1. **Event-as-node.** Each ``GraphNode`` corresponds to exactly one
   ``CognitiveEvent``. Spans are denormalized into start/end node pairs at
   the same parent — matching the storage layout exactly. The renderer can
   collapse visually if it wants to.
2. **Zoom is per-node.** Each node carries its assigned ``zoomLevel`` so the
   API can filter by level without re-running the assignment. ``GET
   /graph?level=2`` is one DB query plus a filter.
3. **Wire format is camelCase**, like everything else under Reverie.
4. **No mutation after build.** ``GraphBundle`` is the immutable output of
   :class:`GraphEngine`; all anomaly/cluster annotations are baked in.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

#: Per the SRS:
#:   L1 = mission view (top-level goals only)         1–5 nodes
#:   L2 = task view (subtasks + major delegations)    5–30 nodes
#:   L3 = operation view (tool calls, memory fetches) 30–200 nodes
#:   L4 = raw view (everything: retries, validations) 200–10k+ nodes
ZoomLevel = Literal[1, 2, 3, 4]
MIN_ZOOM = 1
MAX_ZOOM = 4

#: SRS-defined anomaly categories. Strings rather than an enum so the wire
#: format is human-readable and forward-extensible.
AnomalyKind = Literal[
    "loop",
    "hotspot",
    "bottleneck",
    "poison",
    "explosion",
    "abandon",
]


class _Base(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )


# ---------------------------------------------------------------------------
# Annotations
# ---------------------------------------------------------------------------


class AnomalyAnnotation(_Base):
    """A flag attached to a node by an anomaly detector."""

    kind: AnomalyKind
    severity: Literal["info", "warning", "error"] = "warning"
    detail: str = ""


class ClusterRef(_Base):
    """Reference from a node to the cluster it belongs to."""

    cluster_id: str
    role: Literal["root", "member"] = "member"


# ---------------------------------------------------------------------------
# Nodes and edges
# ---------------------------------------------------------------------------


class GraphNode(_Base):
    """A node in the cognitive DAG.

    One-to-one with a ``CognitiveEvent`` row. Annotation fields default to
    empty/null so callers can filter on them without null-checking.
    """

    id: str  # event id (UUID)
    type: str  # CognitiveEventType
    parent_id: str | None
    depth: int
    timestamp: int

    # Metadata baked in for renderer convenience — saves a separate join.
    duration_ms: float | None
    salience: float | None  # null until Phase 3
    anomaly: bool  # the schema-level boolean (the *event* flagged itself)

    # Phase 2 annotations:
    zoom_level: ZoomLevel
    anomalies: list[AnomalyAnnotation] = Field(default_factory=list)
    cluster: ClusterRef | None = None
    on_critical_path: bool = False

    # Compact one-liner pulled from the payload; useful for tooltip-less UIs.
    label: str = ""


class GraphEdge(_Base):
    """A directed parent→child edge in the cognitive DAG."""

    source: str  # parent event id
    target: str  # child event id
    on_critical_path: bool = False


class GraphCluster(_Base):
    """Grouping of related nodes — typically one cluster per top-level goal."""

    id: str  # synthetic cluster id (matches ``ClusterRef.cluster_id``)
    label: str
    root_event_id: str | None
    member_event_ids: list[str]
    type: Literal["goal", "subagent", "tool_storm", "structural"] = "structural"


class GraphSummary(_Base):
    """Run-level rollup useful in the renderer's HUD."""

    total_nodes: int
    total_edges: int
    nodes_per_zoom: dict[str, int]  # keys: "1", "2", "3", "4"
    anomalies_by_kind: dict[str, int]
    critical_path_length: int


class GraphBundle(_Base):
    """Output of :class:`GraphEngine.build`.

    A fully self-contained representation of the run's cognitive topology,
    safe to send over the wire as a single JSON document.
    """

    run_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    clusters: list[GraphCluster]
    critical_path: list[str]  # ordered event ids from root → leaf failure
    summary: GraphSummary
