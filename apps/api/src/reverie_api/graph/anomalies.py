"""Anomaly detection — six SRS-defined heuristics.

Each detector is a pure function that mutates the matching :class:`GraphNode`
instances in place, appending :class:`AnomalyAnnotation` entries to
``node.anomalies``. Detectors do not interact with each other, so the order
they run in does not matter.

Heuristics (verbatim from SRS section 5, Layer 4):

  LOOP        Same tool + same args within 60 seconds = retry storm.
  HOTSPOT     Any single node consuming >20% of total run tokens.
  BOTTLENECK  Any node with latency > 3x the run median tool latency.
  POISON      Memory retrieval returning <10% relevance score 3+ times.
  EXPLOSION   Subagent spawning more than 8 children.
  ABANDON     Any goal with no child events for > 120 seconds.

Constants are exposed at module level so tests can poke them.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from typing import Any

from reverie_schema import CognitiveEvent

from reverie_api.graph.types import AnomalyAnnotation, GraphNode

# ---------------------------------------------------------------------------
# Tunables (matching SRS verbatim)
# ---------------------------------------------------------------------------

LOOP_WINDOW_MS = 60_000  # 60 s — repeated identical tool calls
HOTSPOT_TOKEN_PCT = 0.20  # 20 % of total run tokens
BOTTLENECK_LATENCY_MULT = 3.0  # 3x the median tool latency
POISON_RELEVANCE_THRESHOLD = 0.10  # <10 % relevance
POISON_HIT_COUNT = 3  # 3+ low-relevance retrievals
EXPLOSION_CHILD_COUNT = 8  # > 8 children
ABANDON_SECONDS = 120  # 120 s with no child


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def annotate_anomalies(
    nodes: list[GraphNode],
    events: list[CognitiveEvent],
) -> None:
    """Run every detector. Mutates ``nodes`` in place."""

    if not nodes:
        return

    by_id: dict[str, GraphNode] = {n.id: n for n in nodes}

    _detect_loops(by_id, events)
    _detect_hotspots(by_id, events)
    _detect_bottlenecks(by_id, events)
    _detect_poison(by_id, events)
    _detect_explosion(by_id, events)
    _detect_abandon(by_id, events)


# ---------------------------------------------------------------------------
# LOOP — same tool + same args within 60s
# ---------------------------------------------------------------------------


def _detect_loops(
    by_id: dict[str, GraphNode],
    events: list[CognitiveEvent],
) -> None:
    """Annotate every ``tool.called`` event that is the second-or-later
    occurrence of (tool_name, args) within a sliding 60-second window."""

    # window: deque of (timestamp, event_id) per (tool_name, args_key).
    last_seen: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)

    for evt in events:
        if evt.type != "tool.called":
            continue
        payload = evt.payload
        if getattr(payload, "kind", None) != "tool":
            continue
        name = getattr(payload, "tool_name", "?")
        args = getattr(payload, "args", {}) or {}
        key = (name, _stable_args_key(args))

        bucket = last_seen[key]
        # Drop entries older than the window.
        cutoff = evt.timestamp - LOOP_WINDOW_MS
        while bucket and bucket[0][0] < cutoff:
            bucket.pop(0)

        if bucket:
            # This is the 2nd-or-later occurrence inside the window — flag it
            # AND back-flag the original occurrence so the loop has both
            # endpoints visible.
            for _, prior_id in bucket:
                node = by_id.get(prior_id)
                if node is not None and not _has_kind(node, "loop"):
                    node.anomalies.append(
                        AnomalyAnnotation(
                            kind="loop",
                            severity="warning",
                            detail=f"identical {name} call repeated within {LOOP_WINDOW_MS // 1000}s",
                        )
                    )
            current = by_id.get(evt.id)
            if current is not None and not _has_kind(current, "loop"):
                current.anomalies.append(
                    AnomalyAnnotation(
                        kind="loop",
                        severity="warning",
                        detail=f"identical {name} call repeated within {LOOP_WINDOW_MS // 1000}s",
                    )
                )
        bucket.append((evt.timestamp, evt.id))


def _stable_args_key(args: Any) -> str:
    """Compact, order-insensitive key for tool args."""

    try:
        return json.dumps(args, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return repr(args)


# ---------------------------------------------------------------------------
# HOTSPOT — single node consuming >20% of total run tokens
# ---------------------------------------------------------------------------


def _detect_hotspots(
    by_id: dict[str, GraphNode],
    events: list[CognitiveEvent],
) -> None:
    """Flag any tool.returned/reasoning.extracted whose token count is more
    than ``HOTSPOT_TOKEN_PCT`` of the run total."""

    per_event: dict[str, int] = {}
    total = 0
    for evt in events:
        tokens = _token_cost(evt)
        if tokens > 0:
            per_event[evt.id] = tokens
            total += tokens
    if total <= 0:
        return

    threshold = HOTSPOT_TOKEN_PCT * total
    for eid, tokens in per_event.items():
        if tokens >= threshold:
            node = by_id.get(eid)
            if node is None or _has_kind(node, "hotspot"):
                continue
            pct = tokens / total * 100
            node.anomalies.append(
                AnomalyAnnotation(
                    kind="hotspot",
                    severity="warning",
                    detail=f"{tokens} tokens ({pct:.1f}% of run total)",
                )
            )


def _token_cost(event: CognitiveEvent) -> int:
    payload = event.payload
    kind = getattr(payload, "kind", None)
    if kind == "tool":
        v = getattr(payload, "token_cost", None)
        return int(v) if isinstance(v, int) else 0
    if kind == "reasoning":
        v = getattr(payload, "tokens_used", None)
        return int(v) if isinstance(v, int) else 0
    return 0


# ---------------------------------------------------------------------------
# BOTTLENECK — latency > 3x run median tool latency
# ---------------------------------------------------------------------------


def _detect_bottlenecks(
    by_id: dict[str, GraphNode],
    events: list[CognitiveEvent],
) -> None:
    """Flag tool.returned events whose latency_ms is more than 3x the run's
    median tool latency."""

    latencies: list[float] = []
    for evt in events:
        if evt.type != "tool.returned":
            continue
        payload = evt.payload
        if getattr(payload, "kind", None) != "tool":
            continue
        v = float(getattr(payload, "latency_ms", 0.0) or 0.0)
        if v > 0:
            latencies.append(v)

    if len(latencies) < 2:
        return  # not enough data for a meaningful median

    median = statistics.median(latencies)
    if median <= 0:
        return
    threshold = BOTTLENECK_LATENCY_MULT * median

    for evt in events:
        if evt.type != "tool.returned":
            continue
        payload = evt.payload
        if getattr(payload, "kind", None) != "tool":
            continue
        v = float(getattr(payload, "latency_ms", 0.0) or 0.0)
        if v < threshold:
            continue
        node = by_id.get(evt.id)
        if node is None or _has_kind(node, "bottleneck"):
            continue
        node.anomalies.append(
            AnomalyAnnotation(
                kind="bottleneck",
                severity="warning",
                detail=(
                    f"latency {v:.1f}ms is {v / median:.1f}x the run "
                    f"median ({median:.1f}ms)"
                ),
            )
        )


# ---------------------------------------------------------------------------
# POISON — memory retrieval returning <10% relevance score 3+ times
# ---------------------------------------------------------------------------


def _detect_poison(
    by_id: dict[str, GraphNode],
    events: list[CognitiveEvent],
) -> None:
    """Flag memory.retrieved events when 3+ retrievals against the same
    storage_key (or query, if no key) return scores below the threshold."""

    weak_count: dict[str, int] = defaultdict(int)
    weak_events: dict[str, list[str]] = defaultdict(list)

    for evt in events:
        if evt.type != "memory.retrieved":
            continue
        payload = evt.payload
        if getattr(payload, "kind", None) != "memory":
            continue
        scores = getattr(payload, "relevance_scores", []) or []
        if not scores:
            continue
        max_score = max(float(s) for s in scores)
        if max_score >= POISON_RELEVANCE_THRESHOLD:
            continue
        key = getattr(payload, "storage_key", None) or getattr(payload, "query", "")
        weak_count[key] += 1
        weak_events[key].append(evt.id)

        if weak_count[key] >= POISON_HIT_COUNT:
            for eid in weak_events[key]:
                node = by_id.get(eid)
                if node is None or _has_kind(node, "poison"):
                    continue
                node.anomalies.append(
                    AnomalyAnnotation(
                        kind="poison",
                        severity="error",
                        detail=(
                            f"memory key {key!r} returned <"
                            f"{POISON_RELEVANCE_THRESHOLD * 100:.0f}% relevance "
                            f"{weak_count[key]} times"
                        ),
                    )
                )


# ---------------------------------------------------------------------------
# EXPLOSION — subagent spawning more than 8 children
# ---------------------------------------------------------------------------


def _detect_explosion(
    by_id: dict[str, GraphNode],
    events: list[CognitiveEvent],
) -> None:
    """Flag any node whose direct children outnumber EXPLOSION_CHILD_COUNT.

    SRS phrasing focuses on subagents but the heuristic generalizes — a
    fanout of >8 from any node is signal regardless of node type.
    """

    children: dict[str, int] = defaultdict(int)
    for evt in events:
        if evt.parent_id is None:
            continue
        children[evt.parent_id] += 1

    for parent_id, count in children.items():
        if count <= EXPLOSION_CHILD_COUNT:
            continue
        node = by_id.get(parent_id)
        if node is None or _has_kind(node, "explosion"):
            continue
        node.anomalies.append(
            AnomalyAnnotation(
                kind="explosion",
                severity="warning",
                detail=f"{count} children (threshold {EXPLOSION_CHILD_COUNT})",
            )
        )


# ---------------------------------------------------------------------------
# ABANDON — goal with no child events for >120s
# ---------------------------------------------------------------------------


def _detect_abandon(
    by_id: dict[str, GraphNode],
    events: list[CognitiveEvent],
) -> None:
    """Flag goals that were created but never produced a child event within
    the abandonment window — and never reached a goal.completed/failed.

    The "now" reference is the last event timestamp in the run. A goal whose
    last child (or self) is older than ABANDON_SECONDS by run-end is flagged.
    """

    if not events:
        return
    now_ts = max(e.timestamp for e in events)

    # For each goal.created, find the latest event in its subtree.
    children_of: dict[str, list[CognitiveEvent]] = defaultdict(list)
    for evt in events:
        if evt.parent_id is not None:
            children_of[evt.parent_id].append(evt)

    # Track goals that ended (completed/failed) — they cannot be abandoned.
    ended_goals: set[str] = set()
    for evt in events:
        if evt.type in {"goal.completed", "goal.failed"}:
            # The goal is identified by parent_id (the start event's id)
            # when the adapter uses the parent-link convention; otherwise
            # by parent linkage we infer the start that this end belongs to.
            # We accept any signal that says "this subtree resolved".
            if evt.parent_id is not None:
                ended_goals.add(evt.parent_id)

    for evt in events:
        if evt.type != "goal.created":
            continue

        # Did this goal get explicitly completed/failed?
        if evt.id in ended_goals:
            continue

        kids = children_of.get(evt.id, [])
        latest = evt.timestamp if not kids else max(k.timestamp for k in kids)
        idle_ms = now_ts - latest
        if idle_ms < ABANDON_SECONDS * 1000:
            continue

        node = by_id.get(evt.id)
        if node is None or _has_kind(node, "abandon"):
            continue
        node.anomalies.append(
            AnomalyAnnotation(
                kind="abandon",
                severity="warning",
                detail=f"no activity for {idle_ms / 1000:.0f}s (threshold {ABANDON_SECONDS}s)",
            )
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_kind(node: GraphNode, kind: str) -> bool:
    return any(a.kind == kind for a in node.anomalies)
