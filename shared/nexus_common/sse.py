"""Server-Sent Events (SSE) support for NEXUS-A2A task streaming."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .protocol import ProgressState

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

    def __init__(self, agent_name: str | None = None, redis_url: str | None = None) -> None:
        self._queues: dict[str, list[asyncio.Queue[SseEvent]]] = {}
        self._agent_name = agent_name or "unknown-agent"
        self._redis_url = redis_url or os.getenv("REDIS_URL")
        self._redis_client: Any | None = None
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

    async def publish(
        self,
        task_id: str,
        event: str,
        data: Any,
        duration_ms: float = 0.0,
        scenario_context: dict[str, Any] | None = None,
        correlation: dict[str, Any] | None = None,
        idempotency: dict[str, Any] | None = None,
        progress: dict[str, Any] | None = None,
    ) -> None:
        """Publish an event to all subscribers for a task and optionally to Redis."""
        if task_id not in self._queues:
            self._queues[task_id] = []
            self._queues[task_id].append(asyncio.Queue())
        for q in self._queues[task_id]:
            await q.put(SseEvent(event=event, data=data))

        # Also publish to Redis for cross-agent monitoring
        await self._publish_to_redis(
            task_id,
            event,
            data,
            duration_ms,
            scenario_context=scenario_context,
            correlation=correlation,
            idempotency=idempotency,
            progress=progress,
        )

    @staticmethod
    def normalize_progress_state(event: str, progress: dict[str, Any] | None) -> dict[str, Any]:
        """Build standardized progress-state contract payload."""
        if progress:
            payload = dict(progress)
            if payload.get("state") == "canceled":
                payload["state"] = "cancelled"
            return ProgressState(
                state=str(payload.get("state", "working")),
                percent=payload.get("percent"),
                eta_ms=payload.get("eta_ms"),
            ).to_dict()

        suffix = event.split(".")[-1].lower().strip()
        if suffix == "canceled":
            suffix = "cancelled"
        if suffix not in {"accepted", "working", "final", "error", "cancelled"}:
            suffix = "working"
        return ProgressState(state=suffix).to_dict()

    def build_event_payload(
        self,
        task_id: str,
        event: str,
        data: Any,
        duration_ms: float,
        scenario_context: dict[str, Any] | None = None,
        correlation: dict[str, Any] | None = None,
        idempotency: dict[str, Any] | None = None,
        progress: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "agent": self._agent_name,
            "task_id": task_id,
            "event": event,
            "data": data if isinstance(data, (dict, str)) else str(data),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
            "progress": self.normalize_progress_state(event, progress),
        }
        if scenario_context:
            payload["scenario_context"] = dict(scenario_context)
        if correlation:
            payload["correlation"] = dict(correlation)
        if idempotency:
            payload["idempotency"] = dict(idempotency)
        return payload

    async def _publish_to_redis(
        self,
        task_id: str,
        event: str,
        data: Any,
        duration_ms: float,
        scenario_context: dict[str, Any] | None = None,
        correlation: dict[str, Any] | None = None,
        idempotency: dict[str, Any] | None = None,
        progress: dict[str, Any] | None = None,
    ) -> None:
        """Publish event to Redis pub/sub channel for command centre."""
        if not self._redis_enabled or not self._redis_client:
            return

        try:
            event_payload = self.build_event_payload(
                task_id,
                event,
                data,
                duration_ms,
                scenario_context=scenario_context,
                correlation=correlation,
                idempotency=idempotency,
                progress=progress,
            )
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

    async def stream_ws(self, task_id: str) -> AsyncIterator[dict[str, Any]]:
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
