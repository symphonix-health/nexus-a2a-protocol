"""In-memory deterministic simulation transport for SDK and CI harnesses."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from typing import Any
from uuid import uuid4

from .streaming import map_nexus_event_to_progress
from .transport import AgentTransport
from .types import TaskEnvelope, TaskEvent, TaskSubmission, TransportError, make_task_event

_ALLOWED_METHODS = {"tasks/send", "tasks/sendSubscribe", "tasks/get", "tasks/cancel"}


class SimulationTransport(AgentTransport):
    """Queue-backed deterministic transport used as a local harness default."""

    def __init__(self, *, agent_id: str = "simulation-agent") -> None:
        self.agent_id = agent_id
        self._queues: dict[str, asyncio.Queue[TaskEvent]] = {}
        self._idempotency_map: dict[str, str] = {}
        self._closed = False

    async def connect(self) -> None:
        self._closed = False

    async def send_task(self, task: TaskEnvelope | Mapping[str, Any]) -> TaskSubmission:
        if self._closed:
            raise TransportError("simulation transport is stopped")

        envelope = TaskEnvelope.from_input(task)
        if envelope.method not in _ALLOWED_METHODS:
            raise TransportError(
                f"Unsupported method: {envelope.method}",
                code=-32601,
            )

        params = dict(envelope.params)
        if params.get("force_auth_error"):
            raise TransportError("Authentication failed", code=-32001, http_status=401)

        idem = params.get("idempotency") if isinstance(params.get("idempotency"), dict) else {}
        idem_key = str(idem.get("idempotency_key") or "").strip()
        if idem_key and idem_key in self._idempotency_map:
            task_id = self._idempotency_map[idem_key]
        else:
            task_id = str(params.get("task_id") or uuid4())
            if idem_key:
                self._idempotency_map[idem_key] = task_id
        queue = self._queues.setdefault(task_id, asyncio.Queue())

        accepted = make_task_event(
            event_type="nexus.task.status",
            payload={"status": {"state": "accepted", "percent": 0}},
            task_id=task_id,
            seq=1,
            agent_id=self.agent_id,
        )
        await queue.put(accepted)

        terminal_error = bool(params.get("force_terminal_error"))
        if terminal_error:
            await queue.put(
                make_task_event(
                    event_type="nexus.task.error",
                    payload={"reason": "simulated_failure"},
                    task_id=task_id,
                    seq=2,
                    agent_id=self.agent_id,
                )
            )
            status = "error"
        else:
            working = make_task_event(
                event_type="nexus.task.status",
                payload={"status": {"state": "working", "percent": 50}},
                task_id=task_id,
                seq=2,
                agent_id=self.agent_id,
            )
            _ = map_nexus_event_to_progress(working, current_progress=0)
            await queue.put(working)
            await queue.put(
                make_task_event(
                    event_type="nexus.task.final",
                    payload={"task_id": task_id, "ok": True},
                    task_id=task_id,
                    seq=3,
                    agent_id=self.agent_id,
                )
            )
            status = "accepted"

        return TaskSubmission(
            task_id=task_id,
            status=status,
            raw_response={
                "jsonrpc": "2.0",
                "id": envelope.request_id,
                "result": {"task_id": task_id, "status": {"state": status}},
            },
        )

    async def stream_events(self, task_id: str) -> AsyncIterator[TaskEvent]:
        queue = self._queues.setdefault(task_id, asyncio.Queue())
        while True:
            evt = await queue.get()
            yield evt
            if evt.is_terminal:
                return

    async def stop(self) -> None:
        self._closed = True
        self._queues.clear()
        self._idempotency_map.clear()
