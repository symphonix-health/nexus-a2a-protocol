"""Server-Sent Events (SSE) support for NEXUS-A2A task streaming."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, Optional

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


@dataclass
class SseEvent:
    """A single SSE event with type and data."""

    event: str
    data: Any


class TaskEventBus:
    """In-process async event bus for task lifecycle events.

    Supports multiple concurrent subscribers per task_id via SSE and WebSocket.
    Optionally publishes events to Redis for cross-agent monitoring.
    """

    def __init__(self, agent_name: Optional[str] = None, redis_url: Optional[str] = None) -> None:
        self._queues: Dict[str, list[asyncio.Queue[SseEvent]]] = {}
        self._agent_name = agent_name or "unknown-agent"
        self._redis_url = redis_url or os.getenv("REDIS_URL")
        self._redis_client: Optional[Any] = None
        self._redis_enabled = False
        
        # Initialize Redis if available
        if REDIS_AVAILABLE and self._redis_url:
            asyncio.create_task(self._init_redis())
    
    async def _init_redis(self) -> None:
        """Initialize Redis connection for pub/sub."""
        try:
            self._redis_client = aioredis.from_url(self._redis_url, decode_responses=True)
            await self._redis_client.ping()
            self._redis_enabled = True
        except Exception:
            self._redis_enabled = False
            self._redis_client = None

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

    async def publish(self, task_id: str, event: str, data: Any, duration_ms: float = 0.0) -> None:
        """Publish an event to all subscribers for a task and optionally to Redis."""
        if task_id not in self._queues:
            self._queues[task_id] = []
            self._queues[task_id].append(asyncio.Queue())
        for q in self._queues[task_id]:
            await q.put(SseEvent(event=event, data=data))
        
        # Also publish to Redis for cross-agent monitoring
        await self._publish_to_redis(task_id, event, data, duration_ms)
    
    async def _publish_to_redis(self, task_id: str, event: str, data: Any, duration_ms: float) -> None:
        """Publish event to Redis pub/sub channel for command centre."""
        if not self._redis_enabled or not self._redis_client:
            return
        
        try:
            event_payload = {
                "agent": self._agent_name,
                "task_id": task_id,
                "event": event,
                "data": data if isinstance(data, (dict, str)) else str(data),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "duration_ms": duration_ms,
            }
            await self._redis_client.publish("nexus:events", json.dumps(event_payload))
        except Exception:
            # Silently fail - Redis is optional
            pass

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
    
    async def close(self) -> None:
        """Close Redis connection if active."""
        if self._redis_client:
            try:
                await self._redis_client.close()
            except Exception:
                pass
