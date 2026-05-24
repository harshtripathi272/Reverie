"""Reverie CognitiveEvent schema — canonical Python (Pydantic v2) definition.

Public surface:

- ``CognitiveEvent`` — the unit of agent observability.
- ``EventPayload`` — discriminated union of payload variants.
- The 11 concrete payload classes (``GoalPayload``, ``ToolPayload``, ...).
- ``Run``, ``RunCreate``, ``RunUpdate`` — run metadata models.
- ``COGNITIVE_EVENT_TYPES`` — tuple of every legal ``CognitiveEvent.type``.
- ``SCHEMA_VERSION`` — the pinned wire-format version, currently ``"1.0"``.

Wire format is camelCase. Python attribute access is snake_case.
"""

from reverie_schema.models import (
    COGNITIVE_EVENT_TYPES,
    MAX_BATCH_SIZE,
    SCHEMA_VERSION,
    CognitiveEvent,
    CognitiveEventType,
    ContextPayload,
    EventPayload,
    GenericPayload,
    GoalPayload,
    MemoryPayload,
    PlannerPayload,
    Priority,
    ReasoningPayload,
    ReflectionPayload,
    RetryPayload,
    Run,
    RunCreate,
    RunStatus,
    RunUpdate,
    Severity,
    SubagentPayload,
    ToolPayload,
    ValidationPayload,
)

__all__ = [
    "COGNITIVE_EVENT_TYPES",
    "MAX_BATCH_SIZE",
    "SCHEMA_VERSION",
    "CognitiveEvent",
    "CognitiveEventType",
    "ContextPayload",
    "EventPayload",
    "GenericPayload",
    "GoalPayload",
    "MemoryPayload",
    "PlannerPayload",
    "Priority",
    "ReasoningPayload",
    "ReflectionPayload",
    "RetryPayload",
    "Run",
    "RunCreate",
    "RunStatus",
    "RunUpdate",
    "Severity",
    "SubagentPayload",
    "ToolPayload",
    "ValidationPayload",
]

__version__ = "0.1.0"
