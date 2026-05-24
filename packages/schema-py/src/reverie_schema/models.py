"""Pydantic v2 models for the Reverie CognitiveEvent schema (v1.0).

Design notes
------------

1. **Wire format is camelCase, code is snake_case.** Every model uses
   ``alias_generator=to_camel`` plus ``populate_by_name=True``, so:

   - JSON in/out uses camelCase (``runId``, ``sessionId``, ``parentId``, ...).
   - Python attribute access uses snake_case (``event.run_id``, ...).
   - Constructors accept either.

2. **Payloads are discriminated by ``_type``.** The literal field is named
   ``kind`` in Python (Pydantic forbids leading-underscore field names) but
   serializes as ``_type`` via an explicit alias, matching the TypeScript
   schema byte-for-byte.

3. **Strict mode (``extra='forbid'``).** Unknown fields fail validation. This
   prevents silent schema drift.

4. **The Zod schema in ``@reverie/schema`` is the parallel source of truth for
   TypeScript.** Any change here must be mirrored there, with a schema-version
   bump if breaking.
"""

from __future__ import annotations

import time
import uuid
from typing import Annotated, Any, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)
from pydantic.alias_generators import to_camel

# ---------------------------------------------------------------------------
# Constants and string-literal types
# ---------------------------------------------------------------------------

SCHEMA_VERSION: Literal["1.0"] = "1.0"

#: Bumping this requires a coordinated change in ``@reverie/schema``.
COGNITIVE_EVENT_TYPES: tuple[str, ...] = (
    "goal.created",
    "goal.completed",
    "goal.failed",
    "tool.called",
    "tool.returned",
    "tool.failed",
    "memory.retrieved",
    "memory.stored",
    "retry.triggered",
    "retry.exhausted",
    "reflection.generated",
    "subagent.spawned",
    "subagent.completed",
    "validation.passed",
    "validation.failed",
    "context.truncated",
    "planner.updated",
    "reasoning.extracted",
)

CognitiveEventType = Literal[
    "goal.created",
    "goal.completed",
    "goal.failed",
    "tool.called",
    "tool.returned",
    "tool.failed",
    "memory.retrieved",
    "memory.stored",
    "retry.triggered",
    "retry.exhausted",
    "reflection.generated",
    "subagent.spawned",
    "subagent.completed",
    "validation.passed",
    "validation.failed",
    "context.truncated",
    "planner.updated",
    "reasoning.extracted",
]

Priority = Literal["critical", "high", "medium", "low"]
Severity = Literal["error", "warning", "info"]
RunStatus = Literal["running", "completed", "failed", "aborted"]

#: Hard upper bound on a single batch ingest call. Mirrors ``MAX_BATCH_SIZE``
#: in ``@reverie/schema``.
MAX_BATCH_SIZE = 1000

# ---------------------------------------------------------------------------
# Base config
# ---------------------------------------------------------------------------


class _Base(BaseModel):
    """Shared config for every Reverie wire-model.

    Both ``populate_by_name=True`` and ``serialize_by_alias`` machinery via
    ``alias_generator=to_camel`` are required so that:

    - Python code constructs models with snake_case kwargs.
    - JSON I/O uses camelCase.
    - Round-tripping is identity.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        # Always emit aliases (camelCase) when dumping to dict/JSON.
        serialize_by_alias=True,
        # Validate on attribute mutation. Slightly slower, but catches bugs.
        validate_assignment=True,
        # Compact JSON.
        ser_json_inf_nan="null",
    )


# ---------------------------------------------------------------------------
# Payloads — each carries a literal ``kind`` (serialized as ``_type``)
# ---------------------------------------------------------------------------


class _PayloadBase(_Base):
    """Base for payload variants.

    Subclasses redeclare ``kind`` with their own ``Literal`` to drive Pydantic's
    discriminated-union dispatch.
    """


class GoalPayload(_PayloadBase):
    kind: Literal["goal"] = Field(default="goal", alias="_type")
    intent: str
    priority: Priority = "medium"
    context: str = ""


class ToolPayload(_PayloadBase):
    kind: Literal["tool"] = Field(default="tool", alias="_type")
    tool_name: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    latency_ms: float = Field(default=0.0, ge=0.0)
    token_cost: int | None = Field(default=None, ge=0)
    success: bool = True
    error_message: str | None = None


class MemoryPayload(_PayloadBase):
    kind: Literal["memory"] = Field(default="memory", alias="_type")
    query: str
    hit_count: int = Field(default=0, ge=0)
    relevance_scores: list[float] = Field(default_factory=list)
    retrieval_ms: float = Field(default=0.0, ge=0.0)
    storage_key: str | None = None


class RetryPayload(_PayloadBase):
    kind: Literal["retry"] = Field(default="retry", alias="_type")
    reason: str
    attempt: int = Field(gt=0)
    max_attempts: int = Field(gt=0)
    previous_error: str
    backoff_ms: float = Field(default=0.0, ge=0.0)


class ReflectionPayload(_PayloadBase):
    kind: Literal["reflection"] = Field(default="reflection", alias="_type")
    insight: str
    triggered_by: str  # source event id
    action_taken: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class SubagentPayload(_PayloadBase):
    kind: Literal["subagent"] = Field(default="subagent", alias="_type")
    agent_type: str
    task: str
    delegated_goal_id: str | None = None
    child_run_id: str | None = None


class ValidationPayload(_PayloadBase):
    kind: Literal["validation"] = Field(default="validation", alias="_type")
    check_name: str
    passed: bool
    severity: Severity = "info"
    details: str = ""


class ContextPayload(_PayloadBase):
    kind: Literal["context"] = Field(default="context", alias="_type")
    tokens_used: int = Field(ge=0)
    token_limit: int = Field(gt=0)
    percent_used: float = Field(ge=0.0, le=100.0)
    truncated_messages: int = Field(ge=0)


class ReasoningPayload(_PayloadBase):
    kind: Literal["reasoning"] = Field(default="reasoning", alias="_type")
    raw_text: str | None = None
    summary: str | None = None
    model_id: str
    tokens_used: int | None = Field(default=None, ge=0)


class PlannerPayload(_PayloadBase):
    kind: Literal["planner"] = Field(default="planner", alias="_type")
    plan: str
    step: int = Field(ge=0)
    total_steps: int | None = Field(default=None, gt=0)
    revision: int = Field(default=0, ge=0)


class GenericPayload(_PayloadBase):
    kind: Literal["generic"] = Field(default="generic", alias="_type")
    data: dict[str, Any] = Field(default_factory=dict)


# Discriminated union — Pydantic uses the ``kind`` field (alias ``_type``) to
# pick the right variant in O(1).
EventPayload = Annotated[
    Union[
        GoalPayload,
        ToolPayload,
        MemoryPayload,
        RetryPayload,
        ReflectionPayload,
        SubagentPayload,
        ValidationPayload,
        ContextPayload,
        ReasoningPayload,
        PlannerPayload,
        GenericPayload,
    ],
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# CognitiveEvent
# ---------------------------------------------------------------------------


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _now_ms() -> int:
    return int(time.time() * 1000)


class CognitiveEvent(_Base):
    """The unit of agent observability.

    Mandatory invariants:

    - ``id`` is a UUID. Adapters should emit v4.
    - ``parent_id`` is ``None`` for the run root. Every other event must point
      to its causal parent.
    - ``depth`` is 0 at the root and monotonically increases down the tree.
    - ``timestamp`` is unix milliseconds.
    - ``schema_version`` is pinned to ``"1.0"``.
    """

    # Identity
    id: str = Field(default_factory=_new_uuid)
    type: CognitiveEventType
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)

    # Topology — mandatory
    parent_id: str | None = None
    depth: int = Field(default=0, ge=0)

    # Timing
    timestamp: int = Field(default_factory=_now_ms, ge=0)
    duration_ms: float | None = Field(default=None, ge=0.0)

    # Payload
    payload: EventPayload

    # Salience
    salience: float | None = Field(default=None, ge=0.0, le=1.0)
    anomaly: bool = False

    schema_version: Literal["1.0"] = SCHEMA_VERSION

    @field_validator("id")
    @classmethod
    def _validate_uuid(cls, v: str) -> str:
        # uuid.UUID raises ValueError for malformed input — let Pydantic wrap
        # it as a validation error.
        uuid.UUID(v)
        return v

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        # Belt-and-suspenders: Literal already enforces this, but being explicit
        # gives a friendlier error on unknown future types.
        if v not in COGNITIVE_EVENT_TYPES:
            raise ValueError(f"unknown event type: {v!r}")
        return v


# ---------------------------------------------------------------------------
# Run metadata
# ---------------------------------------------------------------------------


class RunCreate(_Base):
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    runtime: str = Field(min_length=1)
    started_at: int = Field(ge=0)
    goal: str | None = None


class RunUpdate(_Base):
    """All fields optional — used as a PATCH body."""

    status: RunStatus | None = None
    completed_at: int | None = Field(default=None, ge=0)
    goal: str | None = None


class Run(_Base):
    id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    runtime: str = Field(min_length=1)
    started_at: int = Field(ge=0)
    completed_at: int | None = Field(default=None, ge=0)
    status: RunStatus
    goal: str | None = None
    total_events: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    total_tool_calls: int = Field(default=0, ge=0)
    total_retries: int = Field(default=0, ge=0)
    total_subagents: int = Field(default=0, ge=0)
    pinned: bool = False
    tags: list[str] = Field(default_factory=list)
    created_at: int = Field(ge=0)
