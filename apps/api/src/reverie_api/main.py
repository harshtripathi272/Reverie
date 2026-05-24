"""FastAPI application factory.

The app is built by ``create_app()`` so tests can construct fresh instances
with isolated databases. Production uses the module-level ``app`` instance
(see ``__main__.py``).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from reverie_api import __version__
from reverie_api.broker import EventBroker, get_broker, set_broker
from reverie_api.config import Settings, load_settings
from reverie_api.db import Database, get_database, set_database
from reverie_api.errors import install_exception_handlers
from reverie_api.graph.engine import (
    GraphEngine,
    set_graph_engine,
)
from reverie_api.models import HealthResponse
from reverie_api.routes import events as events_routes
from reverie_api.routes import graph as graph_routes
from reverie_api.routes import replay as replay_routes
from reverie_api.routes import runs as runs_routes
from reverie_api.routes import stream as stream_routes
from reverie_api.snapshot.engine import (
    SnapshotEngine,
    set_snapshot_engine,
)

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a fully-wired FastAPI application.

    A fresh `Database` and `EventBroker` are bound to the app's lifespan, so
    repeated calls produce independent instances — exactly what tests need.
    """

    cfg = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(cfg.db_path)
        await db.connect()
        broker = EventBroker(queue_size=cfg.ws_subscriber_buffer)
        snapshot_engine = SnapshotEngine(db)
        graph_engine = GraphEngine(db)

        set_database(db)
        set_broker(broker)
        set_snapshot_engine(snapshot_engine)
        set_graph_engine(graph_engine)

        # Stash on app.state for tests / introspection.
        app.state.db = db
        app.state.broker = broker
        app.state.snapshot_engine = snapshot_engine
        app.state.graph_engine = graph_engine
        app.state.settings = cfg

        try:
            yield
        finally:
            set_database(None)
            set_broker(None)
            set_snapshot_engine(None)
            set_graph_engine(None)
            await db.close()

    app = FastAPI(
        title="Reverie API",
        version=__version__,
        description="Cognitive observability ingestion backend.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_exception_handlers(app)

    @app.get(
        "/health",
        response_model=HealthResponse,
        response_model_by_alias=True,
        tags=["meta"],
    )
    async def health() -> HealthResponse:
        db = get_database()
        cursor = await db.conn.execute("PRAGMA user_version")
        row = await cursor.fetchone()
        user_version = int(row[0]) if row else 0
        return HealthResponse(version=__version__, db_user_version=user_version)

    app.include_router(runs_routes.router)
    app.include_router(events_routes.router)
    app.include_router(replay_routes.router)
    app.include_router(graph_routes.router)
    app.include_router(stream_routes.router)

    return app


# Module-level instance for production deployment (uvicorn reverie_api.main:app).
app = create_app()
