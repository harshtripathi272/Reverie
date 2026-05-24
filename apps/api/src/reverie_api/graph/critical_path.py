"""Critical-path computation.

Algorithm
---------

1. Pick a "leaf" — the node we want to trace back from:
     - If the run has a failure, use the **first** failure event.
     - Otherwise use the run's last event in timestamp order.
2. Walk ``parent_id`` from the leaf up to a root (``parent_id is None``).
3. Reverse so the result is root-first.

The result is a list of event IDs. The engine later marks these on nodes
and edges. If the leaf has no resolvable ancestor chain (orphan parent),
we return whatever segment we could walk.

For runs with **no events** the function returns an empty list.
"""

from __future__ import annotations

from reverie_schema import CognitiveEvent

from reverie_api.graph.types import GraphEdge, GraphNode

_FAILURE_TYPES = frozenset(
    {
        "goal.failed",
        "tool.failed",
        "validation.failed",
        "retry.exhausted",
    }
)


def compute_critical_path(
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    events: list[CognitiveEvent],
) -> list[str]:
    """Return the ordered list of event IDs on the critical path."""

    del nodes, edges  # we walk parent_id directly via the events list

    if not events:
        return []

    by_id = {e.id: e for e in events}

    leaf = _pick_leaf(events)
    if leaf is None:
        return []

    chain: list[str] = []
    seen: set[str] = set()
    cur = leaf
    while cur is not None:
        if cur.id in seen:
            # Cycle guard — schema forbids this in theory but be safe.
            break
        seen.add(cur.id)
        chain.append(cur.id)
        if cur.parent_id is None:
            break
        cur = by_id.get(cur.parent_id)

    chain.reverse()  # root-first
    return chain


def _pick_leaf(events: list[CognitiveEvent]) -> CognitiveEvent | None:
    """First failure if any, otherwise the latest event by timestamp."""

    for evt in events:
        if evt.type in _FAILURE_TYPES:
            return evt
    return max(events, key=lambda e: e.timestamp)
