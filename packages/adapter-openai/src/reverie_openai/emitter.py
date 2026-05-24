"""Background HTTP emitter.

Architectural rules (in priority order):

1. **Never block the agent.** Public methods are sync and use ``put_nowait``;
   if the queue is full we drop the event and increment a counter.
2. **Never crash the agent.** Network errors, malformed responses, even
   programmer bugs in this module must be caught and logged; the agent runs
   to completion regardless.
3. **Run the asyncio loop in a daemon thread.** The SDK calls our processor
   from arbitrary threads (sync code, asyncio loops, anywhere). The emitter
   owns *its own* event loop so it can use ``httpx.AsyncClient`` cleanly.
4. **Create the httpx client inside the loop.** ``AsyncClient`` is loop-bound;
   creating it in ``__init__`` and using it from another loop is a known
   pitfall the original spec walked into.
5. **Coalesce into batches.** Up to ``batch_size`` events per POST, flushed
   on a soft timer (``flush_interval_ms``). Single-event ingest is supported
   but batches are the fast path.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import sys
import threading
from typing import Any

import httpx
from reverie_schema import CognitiveEvent

from reverie_openai.config import AdapterConfig

logger = logging.getLogger("reverie_openai.emitter")

# Sentinels used to communicate with the background loop without import cycles.
_FLUSH = object()
_SHUTDOWN = object()


class Emitter:
    """Posts CognitiveEvents and run lifecycle calls to the Reverie backend.

    Lifecycle:
        emitter = Emitter(config)
        emitter.start()                     # spawns the background thread
        emitter.create_run(...)             # synchronous-ish (best-effort)
        emitter.emit(event)                 # non-blocking
        emitter.complete_run(...)           # best-effort
        emitter.flush()                     # block until the queue drains
        emitter.shutdown(timeout=2.0)       # flush + stop the loop
    """

    def __init__(self, config: AdapterConfig) -> None:
        self._config = config
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=config.queue_size)
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_ready = threading.Event()
        self._shutdown_complete = threading.Event()

        # Counters exposed for tests + diagnostics.
        self.dropped_count = 0
        self.posted_count = 0
        self.failed_count = 0
        self._consecutive_failures = 0
        self._warned_offline = False

    # ------------------------------------------------------------------ start

    def start(self) -> None:
        if self._thread is not None:
            return
        if self._config.disabled:
            logger.info("reverie_openai disabled via config; emitter is a no-op")
            return

        self._thread = threading.Thread(
            target=self._run_loop,
            name="reverie-openai-emitter",
            daemon=True,
        )
        self._thread.start()
        # Wait briefly for the loop to come up so subsequent calls find it.
        self._loop_ready.wait(timeout=1.0)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        self._loop_ready.set()
        try:
            loop.run_until_complete(self._main())
        except Exception:  # pragma: no cover — defensive
            logger.exception("emitter loop crashed")
        finally:
            try:
                loop.close()
            except Exception:
                pass
            self._shutdown_complete.set()

    async def _main(self) -> None:
        timeout = httpx.Timeout(self._config.request_timeout_seconds)
        async with httpx.AsyncClient(
            base_url=self._config.backend_url,
            timeout=timeout,
            headers=self._config.extra_headers or None,
        ) as client:
            await self._drain_loop(client)

    # ---------------------------------------------------------------- queue

    def _enqueue(self, item: Any) -> bool:
        try:
            self._queue.put_nowait(item)
            return True
        except queue.Full:
            self.dropped_count += 1
            if self.dropped_count == 1 or self.dropped_count % 1000 == 0:
                logger.warning(
                    "reverie_openai: queue full, dropping events (total dropped=%d)",
                    self.dropped_count,
                )
            return False

    # ---------------------------------------------------------------- public

    def emit(self, event: CognitiveEvent) -> None:
        """Queue an event for background dispatch. Non-blocking."""

        if self._config.disabled:
            return
        self._enqueue(("event", event))

    def create_run(self, payload: dict[str, Any]) -> None:
        """Queue a run-create call. Non-blocking."""

        if self._config.disabled:
            return
        self._enqueue(("run_create", payload))

    def update_run(self, run_id: str, payload: dict[str, Any]) -> None:
        if self._config.disabled:
            return
        self._enqueue(("run_update", (run_id, payload)))

    def flush(self, timeout: float = 5.0) -> None:
        """Block until the in-memory queue drains (or timeout elapses)."""

        if self._config.disabled or self._loop is None:
            return
        # Send a flush sentinel; the consumer will set the future when reached.
        loop = self._loop

        async def _wait_drain() -> None:
            # The drain loop processes one item at a time; once it sees this
            # sentinel, everything queued before it has been handled.
            pass

        future = asyncio.run_coroutine_threadsafe(_wait_drain(), loop)
        # Block on the queue itself: re-queue a no-op flush sentinel so the
        # consumer wakes up and processes everything before it.
        ev = threading.Event()
        self._enqueue(("flush", ev))
        ev.wait(timeout=timeout)
        future.cancel()

    def shutdown(self, timeout: float = 5.0) -> None:
        """Flush and stop the background thread. Idempotent.

        Drains remaining queued items synchronously so we don't depend on the
        daemon thread surviving Python's exit. Daemon threads are killed
        immediately on interpreter shutdown — atexit alone is not enough.
        """

        if self._thread is None:
            return

        # First, signal the worker to stop. It will drain any items it can
        # before observing the shutdown sentinel.
        self._enqueue(("shutdown", None))
        self._thread.join(timeout=timeout)

        # Then synchronously drain anything that didn't make it. Even a fast
        # daemon thread can lose the race against process exit on Windows.
        self._sync_drain_remaining()

        self._thread = None
        self._loop = None

    def _sync_drain_remaining(self) -> None:
        """Drain queued items using a synchronous ``httpx.Client``.

        Called from the main thread during shutdown, after the daemon thread
        has had a chance to do its work. This guarantees that any items still
        in the queue make it to the backend before the process exits — the
        daemon thread's async loop can't be relied on past Python shutdown.
        """

        # Pull what's left out of the queue.
        leftover_events: list[CognitiveEvent] = []
        leftover_other: list[Any] = []
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item[0] == "event":
                leftover_events.append(item[1])
            elif item[0] in {"flush", "shutdown"}:
                # Flush waiters — set them so any blocked caller unblocks.
                if item[0] == "flush":
                    try:
                        item[1].set()
                    except Exception:
                        pass
            else:
                leftover_other.append(item)

        if not leftover_events and not leftover_other:
            return

        # Use a SHORT-timeout sync client. We have at most a few seconds
        # before the process really has to exit.
        try:
            with httpx.Client(
                base_url=self._config.backend_url,
                timeout=httpx.Timeout(self._config.request_timeout_seconds),
                headers=self._config.extra_headers or None,
            ) as client:
                # Run-creates and run-updates first (so events have a parent
                # run on the backend).
                run_creates = [it for it in leftover_other if it[0] == "run_create"]
                run_updates = [it for it in leftover_other if it[0] == "run_update"]
                for it in run_creates:
                    self._sync_request(client, "POST", "/api/v1/runs", it[1])
                if leftover_events:
                    body = [e.model_dump(by_alias=True) for e in leftover_events]
                    if self._sync_request(
                        client, "POST", "/api/v1/events/batch", body
                    ):
                        self.posted_count += len(leftover_events)
                for it in run_updates:
                    run_id, body = it[1]
                    self._sync_request(client, "PATCH", f"/api/v1/runs/{run_id}", body)
        except Exception:
            # Truly defensive — never let shutdown raise.
            self.failed_count += 1

    def _sync_request(
        self,
        client: httpx.Client,
        method: str,
        path: str,
        body: Any,
    ) -> bool:
        """Synchronous variant of ``_safe_request``. Never raises."""

        try:
            resp = client.request(method, path, json=body)
        except Exception as exc:
            self._record_failure(f"{method} {path}: {type(exc).__name__}: {exc}")
            return False
        if 200 <= resp.status_code < 300:
            return True
        self._record_failure(
            f"{method} {path}: HTTP {resp.status_code} {resp.text[:200]}"
        )
        return False

    # ---------------------------------------------------------------- consumer

    async def _drain_loop(self, client: httpx.AsyncClient) -> None:
        flush_interval = self._config.flush_interval_ms / 1000.0
        batch: list[CognitiveEvent] = []

        async def _flush_batch() -> None:
            if not batch:
                return
            payload = batch.copy()
            batch.clear()
            await self._post_batch(client, payload)

        while True:
            try:
                # Block briefly for the next item — preserves CPU when idle.
                item = await asyncio.get_running_loop().run_in_executor(
                    None, self._blocking_get, flush_interval
                )
            except RuntimeError:
                break

            if item is None:
                # Timeout — flush any partial batch then loop.
                await _flush_batch()
                continue

            kind = item[0]

            if kind == "event":
                batch.append(item[1])
                # Drain extras opportunistically without re-blocking.
                while not self._queue.empty() and len(batch) < self._config.batch_size:
                    try:
                        peek = self._queue.get_nowait()
                    except queue.Empty:
                        break
                    if peek[0] == "event":
                        batch.append(peek[1])
                    else:
                        # Non-event item: flush events first, then handle it.
                        await _flush_batch()
                        await self._handle(client, peek)
                        if peek[0] == "shutdown":
                            return
                if len(batch) >= self._config.batch_size:
                    await _flush_batch()
                continue

            # All other item kinds: flush events queued before it first.
            await _flush_batch()
            await self._handle(client, item)
            if kind == "shutdown":
                return

    def _blocking_get(self, timeout: float) -> Any | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    async def _handle(self, client: httpx.AsyncClient, item: tuple) -> None:
        kind = item[0]
        if kind == "run_create":
            await self._post_run_create(client, item[1])
        elif kind == "run_update":
            run_id, body = item[1]
            await self._patch_run(client, run_id, body)
        elif kind == "flush":
            ev: threading.Event = item[1]
            ev.set()
        elif kind == "shutdown":
            # Final flush before returning.
            return
        else:
            logger.debug("emitter: unknown queue item kind=%r", kind)

    # ---------------------------------------------------------------- HTTP

    async def _post_run_create(self, client: httpx.AsyncClient, body: dict[str, Any]) -> None:
        await self._safe_request(client, "POST", "/api/v1/runs", body)

    async def _patch_run(
        self, client: httpx.AsyncClient, run_id: str, body: dict[str, Any]
    ) -> None:
        await self._safe_request(client, "PATCH", f"/api/v1/runs/{run_id}", body)

    async def _post_batch(
        self, client: httpx.AsyncClient, events: list[CognitiveEvent]
    ) -> None:
        # Schema-level dump → wire-format JSON list.
        body = [e.model_dump(by_alias=True) for e in events]
        ok = await self._safe_request(client, "POST", "/api/v1/events/batch", body)
        if ok:
            self.posted_count += len(events)

    async def _safe_request(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        body: Any,
    ) -> bool:
        """Issue one request. Never raises. Returns True on 2xx."""

        try:
            resp = await client.request(method, path, json=body)
        except httpx.HTTPError as exc:
            self._record_failure(f"{method} {path}: {type(exc).__name__}: {exc}")
            return False
        except Exception as exc:  # pragma: no cover — really defensive
            self._record_failure(f"{method} {path}: {type(exc).__name__}: {exc}")
            return False

        if 200 <= resp.status_code < 300:
            self._consecutive_failures = 0
            self._warned_offline = False
            return True

        self._record_failure(
            f"{method} {path}: HTTP {resp.status_code} {resp.text[:200]}"
        )
        return False

    def _record_failure(self, message: str) -> None:
        self.failed_count += 1
        self._consecutive_failures += 1
        # Log loudly the first failure of a streak, then go quiet to avoid
        # spamming logs when the backend is offline for the whole run.
        if self._consecutive_failures == 1:
            logger.warning("reverie_openai: %s", message)
        elif self._consecutive_failures == 10 and not self._warned_offline:
            logger.warning(
                "reverie_openai: 10+ consecutive failures; events will continue to be dropped silently."
            )
            self._warned_offline = True
        else:
            logger.debug("reverie_openai (suppressed): %s", message)
