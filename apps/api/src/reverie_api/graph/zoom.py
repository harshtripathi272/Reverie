"""Semantic zoom level assignment.

Pure function over a single :class:`CognitiveEvent`. Returns the lowest
``ZoomLevel`` at which the event becomes visible.

Per the SRS:

  L1 — Mission view: top-level goals only (1–5 nodes)
  L2 — Task view: subtasks + major delegations (5–30 nodes)
  L3 — Operation view: tool calls, memory fetches (30–200 nodes)
  L4 — Raw view: everything else (retries, validations, context) (200–10k+)

The mapping is intentionally conservative on the L1 side and inclusive on
the L4 side. Filtering at level ``N`` means "show all nodes whose
``zoomLevel <= N``".
"""

from __future__ import annotations

from reverie_schema import CognitiveEvent

from reverie_api.graph.types import ZoomLevel

# ---------------------------------------------------------------------------
# Internal classification
# ---------------------------------------------------------------------------

# Event types that are always available at L2 (regardless of depth) because
# they describe major topology — not minutiae.
_L2_TYPES = frozenset(
    {
        "goal.completed",
        "goal.failed",
        "subagent.spawned",
        "subagent.completed",
    }
)

# Event types whose default home is L3 — operation-level detail.
_L3_TYPES = frozenset(
    {
        "tool.called",
        "tool.returned",
        "tool.failed",
        "memory.retrieved",
        "memory.stored",
        "validation.failed",
    }
)

# L4 catch-all (everything not classified above).


def assign_zoom(event: CognitiveEvent) -> ZoomLevel:
    """Return the lowest zoom level at which ``event`` should be visible."""

    type_ = event.type

    # L1 — root-level goal creation only.
    if type_ == "goal.created" and event.depth == 0:
        return 1

    # L2 — anything goal-like at the top of a subtree, plus subagent topology.
    if type_ == "goal.created" and event.depth == 1:
        return 2
    if type_ in _L2_TYPES:
        return 2

    # L3 — operational events.
    if type_ in _L3_TYPES:
        return 3
    if type_ == "goal.created":
        # depth >= 2 — still operational, not raw.
        return 3

    # L4 — raw / noisy / forward-compat unknown.
    return 4
