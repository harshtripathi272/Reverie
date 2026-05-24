"""API request/response shapes layered on top of ``reverie_schema``.

Wire-domain types (``CognitiveEvent``, ``Run``, ``RunCreate``, ``RunUpdate``)
are owned by the schema package. This module only adds wrappers that exist at
the HTTP boundary — pagination envelopes, batch acknowledgements, error bodies.

All models inherit ``alias_generator=to_camel`` so wire format stays camelCase.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from reverie_schema import Run

T = TypeVar("T")


class _Base(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )


class HealthResponse(_Base):
    status: str = "ok"
    version: str
    db_user_version: int


class CreateAck(_Base):
    """Acknowledgement returned by single-event ingest."""

    ok: bool = True
    id: str = Field(..., description="The id of the inserted event")


class BatchAck(_Base):
    """Acknowledgement returned by batch ingest."""

    ok: bool = True
    count: int = Field(..., ge=0, description="Number of events inserted")


class DeleteAck(_Base):
    ok: bool = True
    deleted: bool = True


class PinUpdate(_Base):
    pinned: bool


class Page(_Base, Generic[T]):
    """Paginated list envelope."""

    items: list[T]
    total: int
    limit: int
    offset: int


# Concrete generic alias used by the runs router.
class RunPage(_Base):
    items: list[Run]
    total: int
    limit: int
    offset: int


class ErrorBody(_Base):
    """Structured error response. Always returned on 4xx/5xx."""

    error: str
    detail: str | None = None
    # Optional context (e.g. list of missing run IDs on a batch reject).
    context: dict | None = None
