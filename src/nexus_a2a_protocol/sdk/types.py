"""SDK-level typed envelopes and transport primitives for Nexus A2A."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_id() -> str:
    return uuid4().hex


class TransportError(RuntimeError):
    """Raised when a transport call fails with structured context."""

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        http_status: int | None = None,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.details = details


@dataclass(slots=True)
class TaskEnvelope:
    """Unified outbound task envelope for all SDK transports."""

    method: str = "tasks/sendSubscribe"
    params: dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=_new_id)

    def to_jsonrpc(self) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": self.method,
            "params": dict(self.params),
        }

    @classmethod
    def from_input(cls, payload: TaskEnvelope | Mapping[str, Any]) -> TaskEnvelope:
        if isinstance(payload, TaskEnvelope):
            return cls(
                method=payload.method,
                params=dict(payload.params),
                request_id=payload.request_id,
            )
        if not isinstance(payload, Mapping):
            raise TransportError("task payload must be a mapping")

        method = str(payload.get("method") or "tasks/sendSubscribe").strip()
        if not method:
            method = "tasks/sendSubscribe"

        raw_params = payload.get("params")
        if raw_params is None:
            # Fallback for simple task payloads that do not nest under params.
            params = {k: v for k, v in payload.items() if k not in {"method", "request_id", "token"}}
        elif isinstance(raw_params, Mapping):
            params = dict(raw_params)
        else:
            raise TransportError("task params must be a mapping")

        request_id = str(payload.get("request_id") or _new_id()).strip() or _new_id()
        return cls(method=method, params=params, request_id=request_id)


@dataclass(slots=True)
class TaskSubmission:
    """Normalized send-task response shape for all transports."""

    task_id: str
    status: str
    raw_response: dict[str, Any]


@dataclass(slots=True)
class TaskEvent:
    """Normalized streamed event shape shared by SSE/WS/simulation transports."""

    event_id: str
    timestamp: str
    agent_id: str
    type: str
    payload: Any
    task_id: str | None = None
    seq: int | None = None

    @property
    def is_terminal(self) -> bool:
        return self.type in {"nexus.task.final", "nexus.task.error", "workflow_complete"}


@dataclass(slots=True)
class ProgressUpdate:
    """Progress projection consumed by adapters and harness assertions."""

    progress: int
    total: int = 100
    description: str = ""



def make_task_event(
    *,
    event_type: str,
    payload: Any,
    task_id: str | None = None,
    seq: int | None = None,
    agent_id: str = "unknown-agent",
    event_id: str | None = None,
    timestamp: str | None = None,
) -> TaskEvent:
    return TaskEvent(
        event_id=event_id or _new_id(),
        timestamp=timestamp or _utc_now(),
        agent_id=agent_id,
        type=event_type,
        payload=payload,
        task_id=task_id,
        seq=seq,
    )



def extract_task_id_from_response(response: Mapping[str, Any]) -> str | None:
    result = response.get("result")
    if isinstance(result, Mapping):
        task_id = result.get("task_id")
        if isinstance(task_id, str) and task_id.strip():
            return task_id.strip()

    task_id = response.get("task_id")
    if isinstance(task_id, str) and task_id.strip():
        return task_id.strip()
    return None
