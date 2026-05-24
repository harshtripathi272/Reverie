"""Database layer — async SQLite with append-only event log."""

from reverie_api.db.connection import Database, get_database, set_database
from reverie_api.db.errors import (
    BatchValidationError,
    DatabaseError,
    EventNotFoundError,
    RunNotFoundError,
)

__all__ = [
    "BatchValidationError",
    "Database",
    "DatabaseError",
    "EventNotFoundError",
    "RunNotFoundError",
    "get_database",
    "set_database",
]
