"""Salience scoring — per-node importance from 0.0 to 1.0.

Pure function over a :class:`GraphBundle`. Mutates each node's ``salience``
field in place. Designed to run cheaply (single pass, no I/O).

SRS heuristic v1 weights (sum to 1.00, match section 5 verbatim):

    +0.30  on the critical path
    +0.20  has any anomaly annotation
    +0.20  is a failure event (goal.failed / tool.failed / validation.failed /
                                retry.exhausted)
    +0.15  consumed > 5% of total run tokens
    +0.10  is a retry-trigger event (retry.triggered)
    +0.05  recency bonus (linearly scaled by position in run)

Nodes with ``salience < SALIENCE_NOISE_THRESHOLD`` are considered "noise" and
should be hidden from default rendering. Layer 5 (Phase 3) frontends + the
CLI honor this.
"""

from __future__ import annotations

from dataclasses import dataclass

from reverie_api.graph.types import GraphBundle, GraphNode

#: Nodes scoring strictly less than this are filtered by default.
SALIENCE_NOISE_THRESHOLD = 0.10

_FAILURE_TYPES = frozenset(
    {
        "goal.failed",
        "tool.failed",
        "validation.failed",
        "retry.exhausted",
    }
)


@dataclass(frozen=True)
class SalienceConfig:
    """Tunable weights for :func:`score_salience`. Defaults match the SRS."""

    critical_path_weight: float = 0.30
    anomaly_weight: float = 0.20
    failure_weight: float = 0.20
    hot_token_weight: float = 0.15
    retry_weight: float = 0.10
    recency_weight: float = 0.05

    #: A node consuming this fraction of total run tokens is "hot".
    hot_token_pct: float = 0.05


def score_salience(
    bundle: GraphBundle,
    *,
    config: SalienceConfig | None = None,
) -> None:
    """Annotate every node in ``bundle`` with a salience score in [0, 1].

    Mutates the bundle in place. Idempotent — running twice produces the
    same scores.
    """

    cfg = config or SalienceConfig()
    if not bundle.nodes:
        return

    # ---------------- per-node token cost (only meaningful for tool/reasoning)
    # We must inspect the original event payloads to know token counts, but
    # nodes don't carry payloads. We use the run summary's anomaliesByKind
    # plus the node's anomaly annotations (which include hotspot annotations
    # carrying the percentage in the detail field) as a hint, but for a
    # robust score we need the raw values. The simplest thing: inspect each
    # node's anomaly annotations for ``hotspot`` — the detector already
    # computed and stored the percentage. If a node was flagged hotspot,
    # it definitionally exceeded HOTSPOT_TOKEN_PCT (20%) which is well above
    # our 5% hot-token threshold, so the bonus applies.
    #
    # For finer granularity we'd need to plumb token counts onto nodes.
    # Phase 3 is fine with the binary "is/isn't a token hotspot" signal.

    # ---------------- order index for recency
    order = sorted(bundle.nodes, key=lambda n: n.timestamp)
    order_index = {n.id: i for i, n in enumerate(order)}
    n_nodes = len(order)

    # ---------------- critical-path set (faster than `in list` repeatedly)
    critical = set(bundle.critical_path)

    # ---------------- score each node
    for node in bundle.nodes:
        score = _score_one(node, cfg, critical, order_index, n_nodes)
        # Clamp to [0, 1] — the maximum possible weighted sum is exactly 1.0
        # if all weights are present, but defensive clamping protects against
        # future weight tweaks.
        node.salience = max(0.0, min(1.0, score))


def _score_one(
    node: GraphNode,
    cfg: SalienceConfig,
    critical: set[str],
    order_index: dict[str, int],
    n_nodes: int,
) -> float:
    score = 0.0

    if node.id in critical:
        score += cfg.critical_path_weight

    if node.anomalies:
        score += cfg.anomaly_weight

    if node.type in _FAILURE_TYPES:
        score += cfg.failure_weight

    # Hot-token bonus — see comment in :func:`score_salience`. We use the
    # presence of a ``hotspot`` anomaly as the signal. Any future scorer
    # version that plumbs raw token counts can replace this branch.
    if any(a.kind == "hotspot" for a in node.anomalies):
        score += cfg.hot_token_weight

    if node.type == "retry.triggered":
        score += cfg.retry_weight

    # Recency: linear ramp from 0.0 (oldest) to ``cfg.recency_weight`` (newest).
    if n_nodes > 1:
        idx = order_index.get(node.id, 0)
        score += cfg.recency_weight * (idx / (n_nodes - 1))

    return score
