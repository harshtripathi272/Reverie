"""AI summarization layer (Phase 3 + 4).

Public surface:

- :class:`ClaudeClient` — minimal Anthropic Messages API wrapper. Returns a
  typed :class:`SummaryResult` with provenance so callers can distinguish
  "real summary" from "no key configured" from "API call failed".
- :class:`SummaryService` — DB-backed cache + cluster/region prompt
  templating. Used by Phase 3 (cluster summaries) and Phase 4 (run-pair
  narratives).
"""

from reverie_api.ai.client import (
    ClaudeClient,
    SummaryResult,
    SummaryStatus,
    get_claude_client,
    set_claude_client,
)
from reverie_api.ai.summary import (
    SummaryService,
    get_summary_service,
    set_summary_service,
)

__all__ = [
    "ClaudeClient",
    "SummaryResult",
    "SummaryService",
    "SummaryStatus",
    "get_claude_client",
    "get_summary_service",
    "set_claude_client",
    "set_summary_service",
]
