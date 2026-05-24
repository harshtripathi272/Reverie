"""Salience scoring + AI summarization (Phase 3).

Public surface:

- :func:`score_salience` — pure scorer over a graph bundle.
- :class:`SalienceConfig` — tunable weights (defaults match SRS).
- :class:`SummaryService` — DB-backed AI-summary cache.
- :class:`ClaudeClient` — Anthropic API wrapper. Graceful no-op without a key.
"""

from reverie_api.salience.scorer import (
    SALIENCE_NOISE_THRESHOLD,
    SalienceConfig,
    score_salience,
)

__all__ = [
    "SALIENCE_NOISE_THRESHOLD",
    "SalienceConfig",
    "score_salience",
]
