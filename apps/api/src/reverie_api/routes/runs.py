"""Run management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from reverie_schema import CognitiveEvent, Run, RunCreate, RunUpdate

from reverie_api.db import Database, get_database
from reverie_api.db.errors import RunNotFoundError
from reverie_api.models import DeleteAck, PinUpdate, RunPage

router = APIRouter(prefix="/api/v1", tags=["runs"])


@router.post(
    "/runs",
    status_code=201,
    response_model=Run,
    response_model_by_alias=True,
    summary="Create a new run",
)
async def create_run(
    payload: RunCreate,
    db: Database = Depends(get_database),
) -> Run:
    return await db.create_run(payload)


@router.get(
    "/runs",
    response_model=RunPage,
    response_model_by_alias=True,
    summary="List runs",
)
async def list_runs(
    db: Database = Depends(get_database),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session_id: str | None = Query(default=None, alias="sessionId"),
    status: str | None = Query(default=None),
) -> RunPage:
    items = await db.list_runs(
        limit=limit, offset=offset, session_id=session_id, status=status
    )
    total = await db.count_runs(session_id=session_id, status=status)
    return RunPage(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/runs/{run_id}",
    response_model=Run,
    response_model_by_alias=True,
    summary="Get one run",
)
async def get_run(run_id: str, db: Database = Depends(get_database)) -> Run:
    run = await db.get_run(run_id)
    if run is None:
        raise RunNotFoundError(run_id)
    return run


@router.patch(
    "/runs/{run_id}",
    response_model=Run,
    response_model_by_alias=True,
    summary="Update run status / completedAt / goal",
)
async def update_run(
    run_id: str,
    update: RunUpdate,
    db: Database = Depends(get_database),
) -> Run:
    return await db.update_run(run_id, update)


@router.patch(
    "/runs/{run_id}/pin",
    response_model=Run,
    response_model_by_alias=True,
    summary="Pin or unpin a run",
)
async def update_pinned(
    run_id: str,
    body: PinUpdate,
    db: Database = Depends(get_database),
) -> Run:
    return await db.set_pinned(run_id, body.pinned)


@router.delete(
    "/runs/{run_id}",
    response_model=DeleteAck,
    response_model_by_alias=True,
    summary="Delete a run and all its events",
)
async def delete_run(run_id: str, db: Database = Depends(get_database)) -> DeleteAck:
    await db.delete_run(run_id)
    return DeleteAck()


@router.get(
    "/runs/{run_id}/events",
    response_model=list[CognitiveEvent],
    response_model_by_alias=True,
    summary="Get all events for a run, in timestamp order",
)
async def list_events(
    run_id: str,
    db: Database = Depends(get_database),
    limit: int | None = Query(default=None, ge=1, le=10_000),
    offset: int = Query(default=0, ge=0),
) -> list[CognitiveEvent]:
    return await db.list_events_for_run(run_id, limit=limit, offset=offset)
