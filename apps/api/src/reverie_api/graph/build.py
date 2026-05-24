"""Build a graph bundle from a list of :class:`CognitiveEvent`.

Pure function. No I/O, no side effects. The :class:`GraphEngine` wraps this
with DB plumbing and caching.
"""

from __future__ import annotations

import json
from typing import Any

from reverie_schema import CognitiveEvent

from reverie_api.graph.types import GraphEdge, GraphNode
from reverie_api.graph.zoom import assign_zoom


def _label(event: CognitiveEvent) -> str:
    """One-line readable label for an event. Never raises."""

    payload = event.payload
    kind = getattr(payload, "kind", None)
    if kind == "goal":
        return _trim(getattr(payload, "intent", "") or "goal")
    if kind == "tool":
        name = getattr(payload, "tool_name", "?")
        if getattr(payload, "success", True) is False:
            err = getattr(payload, "error_message", "") or ""
            return _trim(f"{name} → ERROR: {err}")
        return _trim(name)
    if kind == "memory":
        return _trim(f"memory: {getattr(payload, 'query', '')}")
    if kind == "retry":
        return _trim(f"retry {getattr(payload, 'attempt', '?')}: {getattr(payload, 'reason', '')}")
    if kind == "subagent":
        return _trim(f"→ {getattr(payload, 'agent_type', '?')}")
    if kind == "validation":
        passed = "pass" if getattr(payload, "passed", False) else "fail"
        return _trim(f"{getattr(payload, 'check_name', '?')}: {passed}")
    if kind == "reasoning":
        return _trim(getattr(payload, "summary", "") or "(reasoning)")
    if kind == "reflection":
        return _trim(getattr(payload, "insight", "") or "(reflection)")
    if kind == "context":
        return _trim(f"context truncated ({getattr(payload, 'percent_used', 0):.1f}%)")
    if kind == "planner":
        return _trim(f"plan {getattr(payload, 'step', '?')}/{getattr(payload, 'total_steps', '?')}")
    if kind == "generic":
        try:
            data = getattr(payload, "data", {}) or {}
            sdk_type = data.get("sdk_span_type") if isinstance(data, dict) else None
            return _trim(sdk_type or event.type)
        except Exception:
            return _trim(event.type)
    return _trim(event.type)


def _trim(s: Any, *, max_len: int = 80) -> str:
    if s is None:
        return ""
    text = s if isinstance(s, str) else str(s)
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def build_nodes_and_edges(
    events: list[CognitiveEvent],
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Build the node and edge lists from an ordered event sequence.

    Edge construction notes:

    - One edge per ``parent_id`` that resolves to a known event in this run.
      ``parent_id == None`` means "root in this run" — no edge produced.
    - Orphan ``parent_id`` references (i.e. a foreign key into another run, or
      to an event we haven't fetched) are silently skipped. The renderer
      should treat such children as additional roots.
    """

    nodes: list[GraphNode] = []
    known_ids: set[str] = set()
    for evt in events:
        nodes.append(
            GraphNode(
                id=evt.id,
                type=evt.type,
                parent_id=evt.parent_id,
                depth=evt.depth,
                timestamp=evt.timestamp,
                duration_ms=evt.duration_ms,
                salience=evt.salience,
                anomaly=evt.anomaly,
                zoom_level=assign_zoom(evt),
                label=_label(evt),
            )
        )
        known_ids.add(evt.id)

    edges: list[GraphEdge] = []
    for evt in events:
        if evt.parent_id is None:
            continue
        if evt.parent_id in known_ids:
            edges.append(GraphEdge(source=evt.parent_id, target=evt.id))
        # else: orphan — skipped intentionally.

    return nodes, edges
