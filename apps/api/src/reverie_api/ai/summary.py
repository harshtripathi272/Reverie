"""DB-cached AI summarization service.

Used by:

- **Phase 3** — summarize a graph cluster ("what happened in this branch?").
- **Phase 4** — summarize a run-pair comparison ("why did A succeed and B
  fail?").

Cache keying
------------

Rows are keyed by ``(scope, scope_id, content_hash)``:

- ``scope``       — ``"cluster"`` or ``"comparison"`` (extensible).
- ``scope_id``    — for ``cluster``: the cluster's stable id from the graph
                     engine. For ``comparison``: ``"<runA>:<runB>"``.
- ``content_hash`` — SHA-256 of the canonical JSON of the input events. Two
                     identical regions hit the same row even across runs;
                     three runs of the *same* prompt against the same data
                     reuse the same response.

Cache invalidation is handled by content_hash changes — when the underlying
events differ, the hash differs, and a fresh summary is produced.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from reverie_api.ai.client import (
    ClaudeClient,
    SummaryResult,
    SummaryStatus,
)
from reverie_api.db import Database

logger = logging.getLogger(__name__)


_CLUSTER_SYSTEM_PROMPT = (
    "You are an expert AI engineer reviewing the cognitive trace of an "
    "autonomous agent. Given a sequence of cognitive events from one branch "
    "of execution, produce a concise (max 2 sentences) plain-English "
    "explanation of what happened in this branch and why it matters to the "
    "overall run outcome. Be specific about causes and effects. Use no "
    "marketing language. Avoid phrases like 'this trace shows that' — just "
    "state what happened."
)

_COMPARISON_SYSTEM_PROMPT = (
    "You are an expert AI engineer comparing two cognitive traces of "
    "the same agent task — one that succeeded and one that failed (or two "
    "that took different paths). Given the divergence point and the diff "
    "between the two runs, produce a concise (max 3 sentences) plain-English "
    "explanation of why the runs diverged and which run achieved the "
    "better outcome. Be specific about causal chain. No marketing language."
)


class SummaryService:
    """Cache-first AI summary service. Never raises out."""

    def __init__(self, db: Database, client: ClaudeClient) -> None:
        self._db = db
        self._client = client

    # -------------------------------------------------------------- cluster

    async def summarize_cluster(
        self,
        *,
        cluster_id: str,
        events: list[dict[str, Any]],
        force_refresh: bool = False,
    ) -> SummaryResult:
        """Return an AI summary for a cluster of events.

        ``events`` must be the wire-format event dicts (camelCase) for the
        nodes in the cluster.
        """

        return await self._summarize(
            scope="cluster",
            scope_id=cluster_id,
            events=events,
            system_prompt=_CLUSTER_SYSTEM_PROMPT,
            force_refresh=force_refresh,
        )

    async def summarize_comparison(
        self,
        *,
        comparison_id: str,
        diff: dict[str, Any],
        force_refresh: bool = False,
    ) -> SummaryResult:
        """Return an AI narrative for a run-pair comparison.

        ``diff`` is the structured comparison result built by the Phase 4
        compare engine.
        """

        return await self._summarize_text(
            scope="comparison",
            scope_id=comparison_id,
            payload=diff,
            system_prompt=_COMPARISON_SYSTEM_PROMPT,
            force_refresh=force_refresh,
        )

    # -------------------------------------------------------------- internal

    async def _summarize(
        self,
        *,
        scope: str,
        scope_id: str,
        events: list[dict[str, Any]],
        system_prompt: str,
        force_refresh: bool,
    ) -> SummaryResult:
        # Compact the events into something prompt-friendly.
        compact_events = [_compact(e) for e in events]
        return await self._summarize_text(
            scope=scope,
            scope_id=scope_id,
            payload={"events": compact_events},
            system_prompt=system_prompt,
            force_refresh=force_refresh,
        )

    async def _summarize_text(
        self,
        *,
        scope: str,
        scope_id: str,
        payload: dict[str, Any],
        system_prompt: str,
        force_refresh: bool,
    ) -> SummaryResult:
        """Shared cache → API → cache flow."""

        canonical = json.dumps(payload, sort_keys=True, default=str)
        content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        if not force_refresh:
            cached = await self._lookup_cached(scope, scope_id, content_hash)
            if cached is not None:
                return cached

        result = await self._client.summarize(
            system=system_prompt,
            user=canonical,
        )

        # Persist non-disabled rows. We persist failures too (with their
        # status) so repeated calls during an outage don't hammer the API.
        if result.status != "disabled":
            await self._persist(scope, scope_id, content_hash, result)

        return result

    # --------------------------------------------------------------- DB I/O

    async def _lookup_cached(
        self,
        scope: str,
        scope_id: str,
        content_hash: str,
    ) -> SummaryResult | None:
        cursor = await self._db.conn.execute(
            "SELECT text, status, model FROM ai_summaries "
            "WHERE scope = ? AND scope_id = ? AND content_hash = ?",
            (scope, scope_id, content_hash),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        # Only treat ``ok`` rows as authoritative cache hits. Failed rows
        # are kept for accounting but a fresh call should attempt again
        # next time the user asks. Returning the failure here lets the
        # frontend show "we tried but the API was down" without retrying.
        return SummaryResult(
            text=row["text"] or "",
            status=row["status"],  # type: ignore[arg-type]
            model=row["model"],
            detail="from cache" if row["status"] != "ok" else "",
        )

    async def _persist(
        self,
        scope: str,
        scope_id: str,
        content_hash: str,
        result: SummaryResult,
    ) -> None:
        try:
            async with self._db._txn():  # noqa: SLF001
                await self._db.conn.execute(
                    """
                    INSERT INTO ai_summaries (
                        scope, scope_id, content_hash, text, status, model, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(scope, scope_id, content_hash) DO UPDATE
                        SET text = excluded.text,
                            status = excluded.status,
                            model = excluded.model,
                            created_at = excluded.created_at
                    """,
                    (
                        scope,
                        scope_id,
                        content_hash,
                        result.text,
                        result.status,
                        result.model,
                        int(time.time() * 1000),
                    ),
                )
        except Exception:  # pragma: no cover — defensive
            logger.exception(
                "ai_summaries: failed to persist scope=%s scope_id=%s",
                scope,
                scope_id,
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compact(event: dict[str, Any]) -> dict[str, Any]:
    """Strip event dicts down to the fields that matter to the AI.

    The full event blob includes UUIDs and timestamps that are mostly noise
    for a 2-sentence summary. We keep type, depth, label, and short
    payload-derived hints; we drop ids / timestamps / schemaVersion.
    """

    payload = event.get("payload") or {}
    kind = payload.get("_type") if isinstance(payload, dict) else None
    short_payload: dict[str, Any] = {"_type": kind} if kind else {}

    if isinstance(payload, dict):
        if kind == "tool":
            short_payload["toolName"] = payload.get("toolName")
            short_payload["success"] = payload.get("success")
            err = payload.get("errorMessage")
            if err:
                short_payload["errorMessage"] = err
        elif kind == "goal":
            short_payload["intent"] = payload.get("intent")
            short_payload["priority"] = payload.get("priority")
        elif kind == "retry":
            short_payload["reason"] = payload.get("reason")
            short_payload["attempt"] = payload.get("attempt")
        elif kind == "validation":
            short_payload["checkName"] = payload.get("checkName")
            short_payload["passed"] = payload.get("passed")
        elif kind == "subagent":
            short_payload["agentType"] = payload.get("agentType")
        elif kind == "memory":
            short_payload["query"] = payload.get("query")
            short_payload["hitCount"] = payload.get("hitCount")

    return {
        "type": event.get("type"),
        "depth": event.get("depth"),
        "durationMs": event.get("durationMs"),
        "payload": short_payload,
    }


# ---------------------------------------------------------------------------
# DI helpers
# ---------------------------------------------------------------------------

_service_instance: SummaryService | None = None


def set_summary_service(service: SummaryService | None) -> None:
    global _service_instance
    _service_instance = service


def get_summary_service() -> SummaryService:
    if _service_instance is None:
        raise RuntimeError("SummaryService has not been initialised")
    return _service_instance
