"""Server-Sent Events (SSE) support for NEXUS-A2A task streaming."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict


@dataclass
class SseEvent:
    """A single SSE event with type and data."""

    event: str
    data: Any


class TaskEventBus:
    """In-process async event bus for task lifecycle events.

    Supports multiple concurrent subscribers per task_id via SSE and WebSocket.
    """

    def __init__(self) -> None:
        self._queues: Dict[str, list[asyncio.Queue[SseEvent]]] = {}

    def subscribe(self, task_id: str) -> asyncio.Queue[SseEvent]:
        """Create a new subscription queue for a task."""
        if task_id not in self._queues:
            self._queues[task_id] = []
        q: asyncio.Queue[SseEvent] = asyncio.Queue()
        self._queues[task_id].append(q)
        return q

    def get_queue(self, task_id: str) -> asyncio.Queue[SseEvent]:
        """Get or create a default queue for backward compat (single subscriber)."""
        if task_id not in self._queues or not self._queues[task_id]:
            return self.subscribe(task_id)
        return self._queues[task_id][0]

    async def publish(self, task_id: str, event: str, data: Any) -> None:
        """Publish an event to all subscribers for a task."""
        if task_id not in self._queues:
            self._queues[task_id] = []
            self._queues[task_id].append(asyncio.Queue())
        for q in self._queues[task_id]:
            await q.put(SseEvent(event=event, data=data))

    async def stream(self, task_id: str) -> AsyncIterator[str]:
        """Yield SSE-formatted strings for a task until final or error."""
        q = self.subscribe(task_id)
        while True:
            evt = await q.get()
            data = evt.data if isinstance(evt.data, str) else json.dumps(evt.data)
            yield f"event: {evt.event}\ndata: {data}\n\n"
            if evt.event in ("nexus.task.final", "nexus.task.error"):
                break

    async def stream_ws(self, task_id: str) -> AsyncIterator[Dict[str, Any]]:
        """Yield structured event dicts for WebSocket consumers."""
        q = self.subscribe(task_id)
        while True:
            evt = await q.get()
            data = evt.data if isinstance(evt.data, str) else json.dumps(evt.data)
            yield {"event": evt.event, "data": data}
            if evt.event in ("nexus.task.final", "nexus.task.error"):
                break

    def cleanup(self, task_id: str) -> None:
        """Remove all queues for a completed task."""
        self._queues.pop(task_id, None)
