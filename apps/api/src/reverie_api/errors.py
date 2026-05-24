"""Translate domain-layer exceptions into HTTP responses.

Routes raise ``HTTPException`` directly only for things specific to the HTTP
layer (validation, auth). Anything coming up from the data layer goes through
these translators.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from reverie_api.db.errors import (
    BatchValidationError,
    DuplicateEventError,
    DuplicateRunError,
    EventNotFoundError,
    RunNotFoundError,
    RunPinnedError,
)
from reverie_api.models import ErrorBody

logger = logging.getLogger(__name__)


def _body(error: str, detail: str | None = None, context: dict | None = None) -> dict:
    return ErrorBody(error=error, detail=detail, context=context).model_dump(by_alias=True)


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RunNotFoundError)
    async def _run_not_found(_: Request, exc: RunNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=_body("run_not_found", str(exc), {"runId": exc.run_id}),
        )

    @app.exception_handler(EventNotFoundError)
    async def _event_not_found(_: Request, exc: EventNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=_body("event_not_found", str(exc), {"eventId": exc.event_id}),
        )

    @app.exception_handler(DuplicateRunError)
    async def _duplicate_run(_: Request, exc: DuplicateRunError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=_body("duplicate_run", str(exc), {"runId": exc.run_id}),
        )

    @app.exception_handler(RunPinnedError)
    async def _run_pinned(_: Request, exc: RunPinnedError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=_body("run_pinned", str(exc), {"runId": exc.run_id}),
        )

    @app.exception_handler(BatchValidationError)
    async def _batch_invalid(_: Request, exc: BatchValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=_body(
                "batch_unknown_runs",
                str(exc),
                {"missingRunIds": exc.missing_run_ids},
            ),
        )

    @app.exception_handler(DuplicateEventError)
    async def _duplicate_event(_: Request, exc: DuplicateEventError) -> JSONResponse:
        ctx = {"eventId": exc.event_id} if exc.event_id else None
        return JSONResponse(
            status_code=409,
            content=_body("duplicate_event", str(exc), ctx),
        )
