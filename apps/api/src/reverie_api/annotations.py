"""Annotations — user feedback attached to nodes for next-run steering.

After a run finishes, the user can mark nodes in the 3D explorer (or via the
CLI) as ``avoid``, ``focus``, ``done``, or ``note``. On the next run, the
adapter fetches these annotations via ``GET /api/v1/agents/{id}/guidance``
and injects them as a system-prompt prefix so the agent can be steered by
visual feedback rather than only by typed prompts.

This module owns the wire-shape models, the database access methods, and the
guidance-rendering logic. The HTTP routes live in
:mod:`reverie_api.routes.annotations`.

Design notes
------------

- **Pure sidecar data.** Nothing in this module touches the frozen v1.0
  ``CognitiveEvent`` schema. Annotations are an additive layer.
- **Scope is sticky by default.** New annotations have ``scope='agent'`` so
  they carry forward to future runs of the same agent. Use ``scope='run'``
  for one-time-only signals.
- **Two text formats.** The guidance endpoint can render Markdown (for human
  inspection) or a plain prompt prefix (for direct injection). Both are
  produced from the same in-memory representation.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Literal

import aiosqlite
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from reverie_api.db.connection import Database
from reverie_api.db.errors import DatabaseError, RunNotFoundError


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


AnnotationKind = Literal["avoid", "focus", "done", "note"]
AnnotationScope = Literal["agent", "run"]


class _Base(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )


class AnnotationCreate(_Base):
    """Request body for ``POST /api/v1/runs/{id}/annotations``.

    The same shape is used for batch creation. ``runId`` and ``agentId`` are
    derived server-side from the path parameter and the run's stored
    ``agent_id`` respectively, so neither belongs in the request body.
    """

    node_id: str = Field(..., description="The event id this annotation attaches to.")
    kind: AnnotationKind = Field(..., description="Semantic category.")
    note: str | None = Field(default=None, description="Optional free-text.")
    scope: AnnotationScope = Field(default="agent")
    tag: str | None = Field(
        default=None,
        description="Optional topic label so multi-purpose agents can scope guidance.",
    )


class AnnotationBatchCreate(_Base):
    items: list[AnnotationCreate] = Field(..., min_length=1, max_length=500)


class Annotation(_Base):
    """A row from the ``annotations`` table, in wire format."""

    id: str
    run_id: str
    node_id: str
    kind: AnnotationKind
    note: str | None
    scope: AnnotationScope
    agent_id: str
    tag: str | None
    created_at: int


class AnnotationListResponse(_Base):
    items: list[Annotation]


class AnnotationDeleteAck(_Base):
    ok: bool = True
    deleted: int = Field(..., description="Number of rows removed.")


class GuidanceItem(_Base):
    """One annotation, plus the resolved type label of the event it points at.

    The event-type label makes guidance human-readable without needing to
    join into the events table client-side.
    """

    kind: AnnotationKind
    node_id: str
    event_type: str | None
    note: str | None
    tag: str | None
    run_id: str
    created_at: int


class Guidance(_Base):
    """Aggregated, ranked guidance for one agent.

    ``promptPrefix`` is the canonical text to prepend to the agent's
    ``instructions``; ``markdown`` is the same content shaped for humans.
    Both are derived from ``items`` so callers can render them either way.
    """

    agent_id: str
    items: list[GuidanceItem]
    prompt_prefix: str
    markdown: str
    generated_at: int


# ---------------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------------


class AnnotationStore:
    """Read/write annotations.

    Held by the FastAPI app as a singleton via the same dependency-injection
    pattern as :class:`reverie_api.db.connection.Database`. Doesn't open its
    own connection — uses the shared `Database` instance.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def _row_to_annotation(row: aiosqlite.Row) -> Annotation:
        return Annotation(
            id=row["id"],
            run_id=row["run_id"],
            node_id=row["node_id"],
            kind=row["kind"],
            note=row["note"],
            scope=row["scope"],
            agent_id=row["agent_id"],
            tag=row["tag"],
            created_at=row["created_at"],
        )

    # -------------------------------------------------------------- create

    async def create_one(self, run_id: str, payload: AnnotationCreate) -> Annotation:
        """Insert one annotation against ``run_id``.

        Looks up the run's ``agent_id`` so the annotation can later be
        retrieved by agent without a JOIN.
        """

        run = await self._db.get_run(run_id)
        if run is None:
            raise RunNotFoundError(run_id)

        ann = self._build_row(run_id=run_id, agent_id=run.agent_id, payload=payload)
        async with self._db._txn():  # noqa: SLF001 — same package, intentional
            await self._db.conn.execute(
                """
                INSERT INTO annotations (
                    id, run_id, node_id, kind, note, scope, agent_id, tag, created_at
                ) VALUES (
                    :id, :run_id, :node_id, :kind, :note, :scope, :agent_id, :tag, :created_at
                )
                """,
                ann,
            )
        return Annotation(**ann)

    async def create_many(
        self, run_id: str, payloads: list[AnnotationCreate]
    ) -> list[Annotation]:
        """Insert a batch atomically. Cheaper than N round-trips."""

        if not payloads:
            return []
        run = await self._db.get_run(run_id)
        if run is None:
            raise RunNotFoundError(run_id)

        rows = [
            self._build_row(run_id=run_id, agent_id=run.agent_id, payload=p)
            for p in payloads
        ]
        async with self._db._txn():  # noqa: SLF001
            await self._db.conn.executemany(
                """
                INSERT INTO annotations (
                    id, run_id, node_id, kind, note, scope, agent_id, tag, created_at
                ) VALUES (
                    :id, :run_id, :node_id, :kind, :note, :scope, :agent_id, :tag, :created_at
                )
                """,
                rows,
            )
        return [Annotation(**r) for r in rows]

    @staticmethod
    def _build_row(
        *, run_id: str, agent_id: str, payload: AnnotationCreate
    ) -> dict[str, str | int | None]:
        return {
            "id": str(uuid.uuid4()),
            "run_id": run_id,
            "node_id": payload.node_id,
            "kind": payload.kind,
            "note": payload.note,
            "scope": payload.scope,
            "agent_id": agent_id,
            "tag": payload.tag,
            "created_at": int(time.time() * 1000),
        }

    # -------------------------------------------------------------- read

    async def list_for_run(self, run_id: str) -> list[Annotation]:
        run = await self._db.get_run(run_id)
        if run is None:
            raise RunNotFoundError(run_id)
        cursor = await self._db.conn.execute(
            """
            SELECT * FROM annotations
            WHERE run_id = ?
            ORDER BY created_at ASC
            """,
            (run_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_annotation(r) for r in rows]

    async def list_for_agent(
        self,
        agent_id: str,
        *,
        kinds: list[AnnotationKind] | None = None,
        scope: AnnotationScope | None = None,
        tag: str | None = None,
        limit: int = 200,
    ) -> list[Annotation]:
        """Fetch annotations for one agent. Used by guidance resolution.

        Filters
        -------
        - ``kinds``: only these annotation kinds (default: all).
        - ``scope``: only ``agent`` annotations carry forward to the next run.
          When unspecified we still default to ``agent`` to avoid picking up
          one-shot ``run``-scoped notes.
        - ``tag``: only annotations matching this topic.
        - ``limit``: most recent first.
        """

        clauses = ["agent_id = ?"]
        params: list = [agent_id]

        # Default to "agent" scope when not specified — the explicit "run"
        # scope is opt-in and only flows through to the same run's UI.
        if scope is None:
            clauses.append("scope = 'agent'")
        else:
            clauses.append("scope = ?")
            params.append(scope)

        if kinds:
            placeholders = ",".join("?" * len(kinds))
            clauses.append(f"kind IN ({placeholders})")
            params.extend(kinds)

        if tag is not None:
            # Tag match is OR-with-untagged: untagged annotations apply to
            # all topics, so they always show up.
            clauses.append("(tag = ? OR tag IS NULL)")
            params.append(tag)

        params.append(limit)
        cursor = await self._db.conn.execute(
            f"""
            SELECT * FROM annotations
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params,
        )
        rows = await cursor.fetchall()
        return [self._row_to_annotation(r) for r in rows]

    async def list_event_types(self, node_ids: list[str]) -> dict[str, str]:
        """Map a set of event ids to their ``type`` for guidance rendering."""

        if not node_ids:
            return {}
        # Dedupe + chunk to stay under SQLite's parameter limit (~999).
        seen: dict[str, str] = {}
        unique = list(set(node_ids))
        chunk_size = 500
        for i in range(0, len(unique), chunk_size):
            chunk = unique[i : i + chunk_size]
            placeholders = ",".join("?" * len(chunk))
            cursor = await self._db.conn.execute(
                f"SELECT id, type FROM events WHERE id IN ({placeholders})", chunk
            )
            rows = await cursor.fetchall()
            for r in rows:
                seen[r["id"]] = r["type"]
        return seen

    # -------------------------------------------------------------- delete

    async def delete_one(self, annotation_id: str) -> bool:
        """Delete one annotation. Returns True if a row was removed."""

        async with self._db._txn():  # noqa: SLF001
            cursor = await self._db.conn.execute(
                "DELETE FROM annotations WHERE id = ?", (annotation_id,)
            )
        return cursor.rowcount > 0

    async def delete_for_run(self, run_id: str) -> int:
        """Delete all annotations attached to a run. Returns count removed."""

        async with self._db._txn():  # noqa: SLF001
            cursor = await self._db.conn.execute(
                "DELETE FROM annotations WHERE run_id = ?", (run_id,)
            )
        return cursor.rowcount

    async def delete_for_agent(self, agent_id: str) -> int:
        """Delete all annotations for an agent (used by ``guidance --clear``)."""

        async with self._db._txn():  # noqa: SLF001
            cursor = await self._db.conn.execute(
                "DELETE FROM annotations WHERE agent_id = ?", (agent_id,)
            )
        return cursor.rowcount


# ---------------------------------------------------------------------------
# Guidance rendering
# ---------------------------------------------------------------------------


# Caps on how much guidance we render — prevents prompt bloat when a user
# annotates dozens of nodes.
_MAX_PER_KIND = 8


def render_guidance(
    *, agent_id: str, annotations: list[Annotation], event_types: dict[str, str]
) -> Guidance:
    """Build the prompt-prefix and Markdown forms of an agent's guidance.

    Drops ``note`` annotations from the prompt prefix (they're for humans
    only); keeps them in the Markdown view.
    """

    by_kind: dict[str, list[Annotation]] = {"avoid": [], "focus": [], "done": [], "note": []}
    for a in annotations:
        by_kind.setdefault(a.kind, []).append(a)

    items: list[GuidanceItem] = []
    for a in annotations:
        items.append(
            GuidanceItem(
                kind=a.kind,
                node_id=a.node_id,
                event_type=event_types.get(a.node_id),
                note=a.note,
                tag=a.tag,
                run_id=a.run_id,
                created_at=a.created_at,
            )
        )

    prompt_prefix = _render_prompt_prefix(by_kind, event_types)
    markdown = _render_markdown(by_kind, event_types)

    return Guidance(
        agent_id=agent_id,
        items=items,
        prompt_prefix=prompt_prefix,
        markdown=markdown,
        generated_at=int(time.time() * 1000),
    )


def _describe(ann: Annotation, event_type: str | None) -> str:
    """One line summarising an annotation in human-readable form."""

    label = event_type or "event"
    if ann.note:
        return f"{label}: {ann.note}"
    return label


def _render_prompt_prefix(
    by_kind: dict[str, list[Annotation]], event_types: dict[str, str]
) -> str:
    """The text prepended to the agent's `instructions` on the next run."""

    avoid = by_kind.get("avoid", [])[:_MAX_PER_KIND]
    focus = by_kind.get("focus", [])[:_MAX_PER_KIND]
    done = by_kind.get("done", [])[:_MAX_PER_KIND]

    if not (avoid or focus or done):
        return ""

    lines: list[str] = ["PRIOR RUN GUIDANCE FROM USER:"]
    if avoid:
        lines.append("")
        lines.append("Avoid these approaches (the user marked them as dead-ends):")
        for a in avoid:
            lines.append(f"  - {_describe(a, event_types.get(a.node_id))}")
    if focus:
        lines.append("")
        lines.append("Focus on these directions (the user marked them as promising):")
        for a in focus:
            lines.append(f"  - {_describe(a, event_types.get(a.node_id))}")
    if done:
        lines.append("")
        lines.append("Already completed in a prior run (skip these if revisited):")
        for a in done:
            lines.append(f"  - {_describe(a, event_types.get(a.node_id))}")

    return "\n".join(lines)


def _render_markdown(
    by_kind: dict[str, list[Annotation]], event_types: dict[str, str]
) -> str:
    """A Markdown rendering for human inspection (`reverie guidance`)."""

    if not any(by_kind.get(k) for k in ("avoid", "focus", "done", "note")):
        return "_No guidance yet for this agent._"

    sections: list[str] = []

    def emit(title: str, items: list[Annotation]) -> None:
        if not items:
            return
        sections.append(f"### {title}")
        for a in items:
            event_type = event_types.get(a.node_id) or "(event)"
            note = f" — {a.note}" if a.note else ""
            tag = f" [#{a.tag}]" if a.tag else ""
            sections.append(f"- `{event_type}`{tag}{note}")
        sections.append("")

    emit("Avoid", by_kind.get("avoid", []))
    emit("Focus", by_kind.get("focus", []))
    emit("Done", by_kind.get("done", []))
    emit("Notes", by_kind.get("note", []))

    return "\n".join(sections).strip()


# ---------------------------------------------------------------------------
# DI wiring
# ---------------------------------------------------------------------------


_store_instance: AnnotationStore | None = None


def set_annotation_store(store: AnnotationStore | None) -> None:
    global _store_instance
    _store_instance = store


def get_annotation_store() -> AnnotationStore:
    if _store_instance is None:
        raise RuntimeError("AnnotationStore has not been initialised")
    return _store_instance


# Re-exported for tests.
__all__ = [
    "Annotation",
    "AnnotationBatchCreate",
    "AnnotationCreate",
    "AnnotationDeleteAck",
    "AnnotationKind",
    "AnnotationListResponse",
    "AnnotationScope",
    "AnnotationStore",
    "DatabaseError",
    "Guidance",
    "GuidanceItem",
    "RunNotFoundError",
    "get_annotation_store",
    "render_guidance",
    "set_annotation_store",
]
