"""Domain errors raised by the data layer.

Routes catch these and translate to HTTP status codes so that the persistence
layer never imports FastAPI types.
"""

from __future__ import annotations


class DatabaseError(Exception):
    """Base class for all data-layer errors."""


class RunNotFoundError(DatabaseError):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"run not found: {run_id}")
        self.run_id = run_id


class EventNotFoundError(DatabaseError):
    def __init__(self, event_id: str) -> None:
        super().__init__(f"event not found: {event_id}")
        self.event_id = event_id


class BatchValidationError(DatabaseError):
    """Raised when a batch references runs that do not exist.

    The caller is expected to surface ``missing_run_ids`` to the client.
    """

    def __init__(self, missing_run_ids: list[str]) -> None:
        super().__init__(
            f"batch references {len(missing_run_ids)} unknown run(s): "
            + ", ".join(missing_run_ids[:5])
            + ("..." if len(missing_run_ids) > 5 else "")
        )
        self.missing_run_ids = missing_run_ids


class RunPinnedError(DatabaseError):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"run is pinned and cannot be deleted: {run_id}")
        self.run_id = run_id


class DuplicateRunError(DatabaseError):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"run already exists: {run_id}")
        self.run_id = run_id


class DuplicateEventError(DatabaseError):
    """Raised when an event id collides with an existing row.

    The whole batch is rolled back; nothing was persisted.
    """

    def __init__(self, event_id: str | None = None) -> None:
        msg = "event id collision in batch"
        if event_id:
            msg += f": {event_id}"
        super().__init__(msg)
        self.event_id = event_id
