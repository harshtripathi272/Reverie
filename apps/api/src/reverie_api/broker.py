"""In-process pub/sub broker for live event streams.

Each WebSocket subscriber gets a bounded ``asyncio.Queue``. When the queue
fills, new events are dropped for that subscriber (back-pressure) — the
publisher MUST never block ingest because of a slow client.

This is intentionally process-local. Multi-process scaling is a Phase 1+
concern.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from reverie_schema import CognitiveEvent

logger = logging.getLogger(__name__)


class EventBroker:
    """Per-runId fan-out of `CognitiveEvent` to live subscribers."""

    def __init__(self, *, queue_size: int = 10_000) -> None:
        self._queue_size = queue_size
        self._subscribers: dict[str, set[asyncio.Queue[CognitiveEvent]]] = defaultdict(set)
        self._lock = asyncio.Lock()
        # Counters expose back-pressure to operators.
        self._dropped_total = 0

    @property
    def dropped_total(self) -> int:
        return self._dropped_total

    @property
    def subscriber_count(self) -> int:
        return sum(len(s) for s in self._subscribers.values())

    @asynccontextmanager
    async def subscribe(self, run_id: str) -> AsyncIterator[asyncio.Queue[CognitiveEvent]]:
        """Subscribe to events for a single ``run_id``.

        Yields an `asyncio.Queue` that the caller drains. On exit (or any
        exception in the consumer), the queue is removed and any pending
        events are dropped.
        """

        queue: asyncio.Queue[CognitiveEvent] = asyncio.Queue(maxsize=self._queue_size)
        async with self._lock:
            self._subscribers[run_id].add(queue)
        try:
            yield queue
        finally:
            async with self._lock:
                bucket = self._subscribers.get(run_id)
                if bucket is not None:
                    bucket.discard(queue)
                    if not bucket:
                        self._subscribers.pop(run_id, None)

    async def publish(self, event: CognitiveEvent) -> None:
        """Fan out one event. Slow subscribers see drops, never the publisher."""

        # Snapshot the bucket inside the lock; drop the lock before iterating
        # so we never block ingest on a slow consumer.
        async with self._lock:
            bucket = list(self._subscribers.get(event.run_id, ()))

        for queue in bucket:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self._dropped_total += 1
                logger.warning(
                    "broker: dropped event %s for slow subscriber on run %s",
                    event.id,
                    event.run_id,
                )

    async def publish_many(self, events: list[CognitiveEvent]) -> None:
        for evt in events:
            await self.publish(evt)


_broker_instance: EventBroker | None = None


def set_broker(broker: EventBroker | None) -> None:
    global _broker_instance
    _broker_instance = broker


def get_broker() -> EventBroker:
    if _broker_instance is None:
        raise RuntimeError("EventBroker has not been initialised")
    return _broker_instance
