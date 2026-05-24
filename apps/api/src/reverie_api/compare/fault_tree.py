"""Causal fault tree — the chain from a failure back to its root cause.

Identical mechanism to :mod:`graph.critical_path` but exposed under a
comparison-friendly API. We keep the two separate so the comparison
layer can evolve independently.
"""

from __future__ import annotations

from dataclasses import dataclass

from reverie_schema import CognitiveEvent


@dataclass(frozen=True)
class FaultTree:
    """Result of walking ``parent_id`` from a failure event back to root."""

    failure_event_id: str
    chain_event_ids: list[str]  # root-first
    root_event_id: str | None


def build_fault_tree(
    *,
    failure_event: CognitiveEvent,
    events: list[CognitiveEvent],
) -> FaultTree:
    """Walk ``parent_id`` from ``failure_event`` to the root.

    Returns a :class:`FaultTree` with the chain in root-first order. If the
    failure event has no resolvable ancestor (orphan parent), the chain is
    just the failure itself.
    """

    by_id = {e.id: e for e in events}
    chain: list[str] = []
    seen: set[str] = set()
    cur: CognitiveEvent | None = failure_event
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        chain.append(cur.id)
        if cur.parent_id is None:
            break
        cur = by_id.get(cur.parent_id)

    chain.reverse()
    return FaultTree(
        failure_event_id=failure_event.id,
        chain_event_ids=chain,
        root_event_id=chain[0] if chain else None,
    )
