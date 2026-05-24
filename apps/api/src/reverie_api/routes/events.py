"""Event ingestion endpoints — single + batch.

Latency target (single insert): < 5 ms p50 on a warm SQLite WAL.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from reverie_schema import CognitiveEvent

from reverie_api.broker import EventBroker, get_broker
from reverie_api.db import Database, get_database
from reverie_api.models import BatchAck, CreateAck

# Mirrors @reverie/schema's MAX_BATCH_SIZE.
MAX_BATCH_SIZE = 1000

router = APIRouter(prefix="/api/v1", tags=["events"])


@router.post(
    "/events",
    status_code=201,
    response_model=CreateAck,
    response_model_by_alias=True,
    summary="Ingest a single event",
)
async def ingest_event(
    event: CognitiveEvent,
    db: Database = Depends(get_database),
    broker: EventBroker = Depends(get_broker),
) -> CreateAck:
    await db.insert_event(event)
    # Broadcast after persistence — subscribers should never see an event
    # that isn't durable.
    await broker.publish(event)
    return CreateAck(id=event.id)


@router.post(
    "/events/batch",
    status_code=201,
    response_model=BatchAck,
    response_model_by_alias=True,
    summary="Ingest up to 1000 events atomically",
)
async def ingest_batch(
    events: list[CognitiveEvent],
    db: Database = Depends(get_database),
    broker: EventBroker = Depends(get_broker),
) -> BatchAck:
    if not events:
        raise HTTPException(status_code=400, detail="batch must contain at least one event")
    if len(events) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"batch exceeds maximum size of {MAX_BATCH_SIZE} events",
        )

    count = await db.insert_events(events)
    await broker.publish_many(events)
    return BatchAck(count=count)
