"""Semantic alignment of two run event sequences.

Algorithm: classic **Needleman-Wunsch** sequence alignment with a custom
similarity function over :class:`CognitiveEvent` instances. Output is a
list of aligned pairs — each pair is either ``(event_a, event_b)`` (a
match), ``(event_a, None)`` (an event in A with no counterpart in B), or
``(None, event_b)`` (an event in B with no counterpart in A).

Why Needleman-Wunsch
--------------------

Index-based alignment fails the moment one run has extra retries — every
subsequent event shifts. Greedy "match by type" produces ambiguities. NW is
deterministic, optimal under its scoring matrix, and runs in O(|A| × |B|)
which is fine for runs of a few hundred events. For runs in the thousands,
we'd switch to a banded variant; not needed yet.

Similarity scoring
------------------

The matrix favors:
  +1.0  same event type AND same payload identity (tool name, goal intent)
  +0.7  same event type, different identity
  +0.3  same payload _type, different event type (e.g. tool.called vs tool.returned)
  -0.5  different (gap/mismatch penalty)
  -0.3  insertion / deletion (gap)

These weights produce intuitively correct alignments on the runs we've
hand-tested. They are tunable via :class:`AlignmentConfig`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from reverie_schema import CognitiveEvent

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

PairKind = Literal["match", "only_a", "only_b"]


@dataclass(frozen=True)
class AlignmentPair:
    """One row of the alignment.

    Exactly one of ``a_index`` and ``b_index`` is None for ``only_*`` rows;
    both are set for ``match`` rows.
    """

    kind: PairKind
    a_index: int | None
    b_index: int | None
    similarity: float


@dataclass(frozen=True)
class AlignmentResult:
    """Full alignment between two event sequences."""

    pairs: list[AlignmentPair]
    score: float

    @property
    def matched_count(self) -> int:
        return sum(1 for p in self.pairs if p.kind == "match")

    @property
    def only_a_count(self) -> int:
        return sum(1 for p in self.pairs if p.kind == "only_a")

    @property
    def only_b_count(self) -> int:
        return sum(1 for p in self.pairs if p.kind == "only_b")


@dataclass(frozen=True)
class AlignmentConfig:
    same_type_same_identity: float = 1.0
    same_type_different_identity: float = 0.7
    same_kind_different_type: float = 0.3
    mismatch_penalty: float = -0.5
    gap_penalty: float = -0.3


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------


def event_similarity(
    a: CognitiveEvent,
    b: CognitiveEvent,
    *,
    config: AlignmentConfig | None = None,
) -> float:
    """Return a similarity score in [-1.0, 1.0] between two events."""

    cfg = config or AlignmentConfig()

    if a.type == b.type:
        if _identity_matches(a, b):
            return cfg.same_type_same_identity
        return cfg.same_type_different_identity

    if _payload_kind(a) == _payload_kind(b):
        return cfg.same_kind_different_type

    return cfg.mismatch_penalty


def _payload_kind(event: CognitiveEvent) -> str | None:
    return getattr(event.payload, "kind", None)


def _identity_matches(a: CognitiveEvent, b: CognitiveEvent) -> bool:
    """Two events have the *same identity* if their payloads describe the
    same logical operation. Specifically:

    - tool events: same ``toolName``
    - goal events: same ``intent``
    - memory: same ``query``
    - subagent: same ``agentType``
    - validation: same ``checkName``
    - other kinds: only type-matches.
    """

    pa, pb = a.payload, b.payload
    kind = getattr(pa, "kind", None)
    if kind != getattr(pb, "kind", None):
        return False
    if kind == "tool":
        return getattr(pa, "tool_name", None) == getattr(pb, "tool_name", None)
    if kind == "goal":
        return getattr(pa, "intent", None) == getattr(pb, "intent", None)
    if kind == "memory":
        return getattr(pa, "query", None) == getattr(pb, "query", None)
    if kind == "subagent":
        return getattr(pa, "agent_type", None) == getattr(pb, "agent_type", None)
    if kind == "validation":
        return getattr(pa, "check_name", None) == getattr(pb, "check_name", None)
    return True


# ---------------------------------------------------------------------------
# Needleman-Wunsch
# ---------------------------------------------------------------------------


def align_runs(
    a: list[CognitiveEvent],
    b: list[CognitiveEvent],
    *,
    config: AlignmentConfig | None = None,
) -> AlignmentResult:
    """Align two event sequences. Returns an :class:`AlignmentResult`."""

    cfg = config or AlignmentConfig()
    n, m = len(a), len(b)

    # Trivial early exits.
    if n == 0 and m == 0:
        return AlignmentResult(pairs=[], score=0.0)
    if n == 0:
        return AlignmentResult(
            pairs=[AlignmentPair("only_b", None, j, 0.0) for j in range(m)],
            score=cfg.gap_penalty * m,
        )
    if m == 0:
        return AlignmentResult(
            pairs=[AlignmentPair("only_a", i, None, 0.0) for i in range(n)],
            score=cfg.gap_penalty * n,
        )

    # ---- Build the DP table.
    # score[i][j] = best alignment score for a[:i] vs b[:j]
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        score[i][0] = score[i - 1][0] + cfg.gap_penalty
    for j in range(1, m + 1):
        score[0][j] = score[0][j - 1] + cfg.gap_penalty

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sim = event_similarity(a[i - 1], b[j - 1], config=cfg)
            diag = score[i - 1][j - 1] + sim
            up = score[i - 1][j] + cfg.gap_penalty
            left = score[i][j - 1] + cfg.gap_penalty
            score[i][j] = max(diag, up, left)

    # ---- Trace back to recover the alignment.
    pairs: list[AlignmentPair] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            sim = event_similarity(a[i - 1], b[j - 1], config=cfg)
            if score[i][j] == score[i - 1][j - 1] + sim:
                pairs.append(
                    AlignmentPair("match", i - 1, j - 1, sim)
                )
                i -= 1
                j -= 1
                continue
        if i > 0 and (j == 0 or score[i][j] == score[i - 1][j] + cfg.gap_penalty):
            pairs.append(AlignmentPair("only_a", i - 1, None, 0.0))
            i -= 1
            continue
        # else step left
        pairs.append(AlignmentPair("only_b", None, j - 1, 0.0))
        j -= 1

    pairs.reverse()
    return AlignmentResult(pairs=pairs, score=score[n][m])
