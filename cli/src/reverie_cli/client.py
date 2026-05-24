"""Thin HTTP client used by CLI commands.

We keep this synchronous — the CLI's request count per invocation is small
and sync code reads more naturally for top-level scripts. ``httpx.Client``
gives us the same retry/timeout knobs as the async variant.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import httpx


DEFAULT_TIMEOUT = httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=5.0)


class ReverieClient:
    """Minimal client over the Reverie REST API."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: httpx.Timeout | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout or DEFAULT_TIMEOUT,
            headers={"User-Agent": "reverie-cli/0.1.0"},
        )

    # -------------------------------------------------------------- lifecycle

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ReverieClient":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    # ------------------------------------------------------------------ meta

    def health(self) -> dict[str, Any]:
        return self._get("/health")

    # ------------------------------------------------------------------ runs

    def list_runs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        session_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if session_id is not None:
            params["sessionId"] = session_id
        if status is not None:
            params["status"] = status
        return self._get("/api/v1/runs", params=params)

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._get(f"/api/v1/runs/{run_id}")

    def get_events(
        self,
        run_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"offset": offset}
        if limit is not None:
            params["limit"] = limit
        return self._get(f"/api/v1/runs/{run_id}/events", params=params)

    # ------------------------------------------------------------------ http

    def _get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()


@contextmanager
def open_client(base_url: str) -> Iterator[ReverieClient]:
    client = ReverieClient(base_url)
    try:
        yield client
    finally:
        client.close()
