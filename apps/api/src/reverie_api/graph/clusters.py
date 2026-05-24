"""Cluster construction.

Pure function over the (already built) node and edge lists. No event log
required — clustering is a topological property.

Rules (SRS section 5):

1. Each top-level goal (``goal.created`` at depth 0) starts a **"goal"**
   cluster containing every descendant.
2. Each ``subagent.spawned`` event starts a **"subagent"** cluster
   (sub-cluster of its enclosing goal cluster, if any).
3. Repeated identical tool calls (already flagged with ``loop`` anomaly) are
   collapsed into a **"tool_storm"** cluster keyed on tool name.
4. Anything still uncovered (retries with no parent goal, orphans, etc.)
   becomes part of a single ``"structural"`` catch-all so the renderer
   doesn't have to special-case it.

The clusters do NOT partition the node set — a node can belong to a goal
cluster AND a tool_storm. The renderer picks which to show based on the
current zoom level.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict

from reverie_api.graph.types import GraphCluster, GraphEdge, GraphNode


def build_clusters(
    nodes: list[GraphNode],
    edges: list[GraphEdge],
) -> list[GraphCluster]:
    """Return the cluster list for the graph."""

    if not nodes:
        return []

    by_id = {n.id: n for n in nodes}
    children: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        children[e.source].append(e.target)

    clusters: list[GraphCluster] = []
    assigned: set[str] = set()

    # ---- 1) Goal clusters: rooted at depth-0 goal.created events. --------
    goal_roots = [n for n in nodes if n.type == "goal.created" and n.depth == 0]
    for root in goal_roots:
        members = _descendants(root.id, children)
        members_with_root = [root.id, *members]
        cid = _cluster_id("goal", root.id)
        clusters.append(
            GraphCluster(
                id=cid,
                label=root.label or "goal",
                root_event_id=root.id,
                member_event_ids=members_with_root,
                type="goal",
            )
        )
        assigned.update(members_with_root)

    # ---- 2) Subagent clusters: rooted at subagent.spawned events. --------
    subagent_roots = [n for n in nodes if n.type == "subagent.spawned"]
    for root in subagent_roots:
        members = _descendants(root.id, children)
        members_with_root = [root.id, *members]
        cid = _cluster_id("subagent", root.id)
        clusters.append(
            GraphCluster(
                id=cid,
                label=root.label or "subagent",
                root_event_id=root.id,
                member_event_ids=members_with_root,
                type="subagent",
            )
        )
        # subagent membership is layered on top of goal membership; we do
        # NOT mark these in ``assigned`` so the catch-all below stays small.

    # ---- 3) Tool storms: nodes already flagged ``loop`` grouped by name. -
    by_tool: dict[str, list[GraphNode]] = defaultdict(list)
    for n in nodes:
        if any(a.kind == "loop" for a in n.anomalies):
            # Tool name is the first word of the label (we set it that way
            # in build._label).
            tool_name = (n.label or n.type).split(" ")[0]
            by_tool[tool_name].append(n)
    for tool_name, group in by_tool.items():
        if len(group) < 2:
            continue
        cid = _cluster_id("tool_storm", tool_name)
        clusters.append(
            GraphCluster(
                id=cid,
                label=f"loop: {tool_name}",
                root_event_id=group[0].id,
                member_event_ids=[n.id for n in group],
                type="tool_storm",
            )
        )

    # ---- 4) Structural catch-all for anything still unassigned. ---------
    leftover = [n.id for n in nodes if n.id not in assigned]
    if leftover:
        cid = _cluster_id("structural", "leftover")
        clusters.append(
            GraphCluster(
                id=cid,
                label="other",
                root_event_id=None,
                member_event_ids=leftover,
                type="structural",
            )
        )

    return clusters


def _descendants(root_id: str, children: dict[str, list[str]]) -> list[str]:
    """Iterative DFS — no recursion to avoid Python's stack limit on huge
    runs."""

    out: list[str] = []
    stack = list(children.get(root_id, []))
    seen: set[str] = set()
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        out.append(cur)
        stack.extend(children.get(cur, []))
    return out


def _cluster_id(kind: str, key: str) -> str:
    """Stable cluster id from kind + key. Truncated to keep wire bytes
    small, full-length hash lives in the digest."""

    h = hashlib.sha1(f"{kind}:{key}".encode("utf-8")).hexdigest()[:12]
    return f"{kind}-{h}"
