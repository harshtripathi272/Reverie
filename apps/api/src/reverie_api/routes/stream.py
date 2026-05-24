"""Live event stream over WebSocket.

Connect to ``ws://<host>/stream?runId=<id>``. The server sends one JSON
``CognitiveEvent`` per message, in the order events are persisted. Slow
clients are not blocked at the broker level; instead, events are dropped
and a server-side counter is incremented.

The connection is read-only — incoming messages are ignored except as a
liveness signal. Closing the WebSocket cleanly unsubscribes.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from reverie_api.broker import get_broker
from reverie_api.db import get_database

logger = logging.getLogger(__name__)

router = APIRouter()

# Periodic ping so dead TCP connections are detected promptly.
_PING_INTERVAL_SECONDS = 30.0


@router.websocket("/stream")
async def stream(
    websocket: WebSocket,
    run_id: str = Query(..., alias="runId"),
) -> None:
    db = get_database()
    broker = get_broker()

    # Reject early on unknown runs so adapters get a clean error.
    run = await db.get_run(run_id)
    if run is None:
        await websocket.close(code=1008, reason=f"unknown run: {run_id}")
        return

    await websocket.accept()

    async with broker.subscribe(run_id) as queue:
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=_PING_INTERVAL_SECONDS
                    )
                except asyncio.TimeoutError:
                    # Send a keepalive ping. websocket.send_text("") is fine
                    # but a typed envelope is more useful for clients.
                    await websocket.send_text(json.dumps({"_kind": "ping"}))
                    continue

                # Pydantic dump → JSON via aliases (camelCase wire format).
                payload = event.model_dump_json()
                await websocket.send_text(payload)
        except WebSocketDisconnect:
            return
        except Exception:  # pragma: no cover — defensive
            logger.exception("stream: unexpected error on run %s", run_id)
            try:
                await websocket.close(code=1011)
            except Exception:
                pass
