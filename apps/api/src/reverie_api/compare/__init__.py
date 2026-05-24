"""Run-pair comparative debugger (Phase 4).

Public surface:

- :func:`align_runs` — semantic event alignment via Needleman-Wunsch.
- :func:`compute_diff` — token / tool / memory / retry diffs between two runs.
- :func:`build_fault_tree` — causal chain from a failure back to its root.
- :class:`CompareEngine` — orchestrates the above + AI narrative generation.
"""

from reverie_api.compare.align import (
    AlignmentPair,
    AlignmentResult,
    align_runs,
    event_similarity,
)
from reverie_api.compare.diff import (
    ComparisonDiff,
    DivergencePoint,
    compute_diff,
)
from reverie_api.compare.engine import (
    CompareEngine,
    get_compare_engine,
    set_compare_engine,
)
from reverie_api.compare.fault_tree import FaultTree, build_fault_tree

__all__ = [
    "AlignmentPair",
    "AlignmentResult",
    "CompareEngine",
    "ComparisonDiff",
    "DivergencePoint",
    "FaultTree",
    "align_runs",
    "build_fault_tree",
    "compute_diff",
    "event_similarity",
    "get_compare_engine",
    "set_compare_engine",
]
