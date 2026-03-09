"""Deterministic in-process runtime used by the SDK harness mock mode."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, StreamingResponse
except Exception as exc:  # pragma: no cover - optional dependency
    FastAPI = None  # type: ignore[assignment]
    Request = Any  # type: ignore[misc,assignment]
    JSONResponse = None  # type: ignore[assignment]
    StreamingResponse = None  # type: ignore[assignment]
    _FASTAPI_IMPORT_ERROR = exc
else:
    _FASTAPI_IMPORT_ERROR = None


@dataclass(slots=True)
class MockNexusRuntime:
    """Task lifecycle runtime with deterministic responses for harness tests."""

    required_token: str = "mock-token"
    agent_id: str = "mock-runtime"
    tasks: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    idempotency_map: dict[str, str] = field(default_factory=dict)

    def _auth_ok(self, token: str | None) -> bool:
        if token is None:
            return False
        return token.strip() == self.required_token

    def _error_envelope(self, rid: str, code: int, message: str, reason: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "error": {
                "code": code,
                "message": message,
                "data": {"reason": reason},
            },
        }

    def _build_events(self, task_id: str, *, terminal_error: bool = False) -> list[dict[str, Any]]:
        events = [
            {
                "event_id": f"evt-{task_id}-1",
                "event": "nexus.task.status",
                "seq": 1,
                "task_id": task_id,
                "timestamp": "2026-01-01T00:00:00Z",
                "data": {"status": {"state": "accepted", "percent": 0}},
            }
        ]
        if terminal_error:
            events.append(
                {
                    "event_id": f"evt-{task_id}-2",
                    "event": "nexus.task.error",
                    "seq": 2,
                    "task_id": task_id,
                    "timestamp": "2026-01-01T00:00:01Z",
                    "data": {"reason": "simulated_failure"},
                }
            )
            return events

        events.append(
            {
                "event_id": f"evt-{task_id}-2",
                "event": "nexus.task.status",
                "seq": 2,
                "task_id": task_id,
                "timestamp": "2026-01-01T00:00:01Z",
                "data": {"status": {"state": "working", "percent": 55}},
            }
        )
        events.append(
            {
                "event_id": f"evt-{task_id}-3",
                "event": "nexus.task.final",
                "seq": 3,
                "task_id": task_id,
                "timestamp": "2026-01-01T00:00:02Z",
                "data": {"task_id": task_id, "ok": True},
            }
        )
        return events

    def issue_task(
        self,
        *,
        method: str,
        params: dict[str, Any],
        request_id: str,
        token: str | None,
    ) -> tuple[int, dict[str, Any]]:
        if not self._auth_ok(token):
            return 401, self._error_envelope(request_id, -32001, "Unauthorized", "auth_failed")

        if method not in {"tasks/send", "tasks/sendSubscribe", "tasks/get", "tasks/cancel"}:
            return 200, self._error_envelope(request_id, -32601, "Method not found", "method_not_found")

        if method == "tasks/get":
            task_id = str(params.get("task_id") or "").strip()
            if not task_id or task_id not in self.tasks:
                return 200, self._error_envelope(request_id, -32002, "Task not found", "task_not_found")
            return 200, {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "task_id": task_id,
                    "status": {"state": "completed"},
                },
            }

        idem = params.get("idempotency") if isinstance(params.get("idempotency"), dict) else {}
        idem_key = str(idem.get("idempotency_key") or "").strip()
        if idem_key and idem_key in self.idempotency_map:
            task_id = self.idempotency_map[idem_key]
        else:
            task_id = str(params.get("task_id") or uuid4())
            if idem_key:
                self.idempotency_map[idem_key] = task_id

        terminal_error = bool(params.get("force_terminal_error"))
        self.tasks[task_id] = self._build_events(task_id, terminal_error=terminal_error)

        return 200, {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "task_id": task_id,
                "status": {"state": "accepted"},
                "transport_used": "mock",
            },
        }

    async def sse_frames(self, task_id: str) -> AsyncIterator[str]:
        for evt in self.tasks.get(task_id, []):
            yield (
                f"id: {evt.get('seq')}\n"
                f"event: {evt.get('event')}\n"
                f"data: {json.dumps(evt.get('data', {}))}\n\n"
            )

    def websocket_messages(self, task_id: str) -> list[str]:
        messages: list[str] = []
        for evt in self.tasks.get(task_id, []):
            messages.append(
                json.dumps(
                    {
                        "event_id": evt.get("event_id"),
                        "timestamp": evt.get("timestamp"),
                        "event": evt.get("event"),
                        "task_id": evt.get("task_id"),
                        "seq": evt.get("seq"),
                        "data": evt.get("data"),
                    }
                )
            )
        return messages

    def build_app(self) -> FastAPI:
        if FastAPI is None:
            raise RuntimeError(f"FastAPI is required for mock runtime: {_FASTAPI_IMPORT_ERROR}")

        app = FastAPI(title="sdk-harness-mock-runtime")

        @app.get("/health")
        async def health() -> JSONResponse:
            return JSONResponse(content={"status": "healthy", "agent": self.agent_id})

        @app.get("/.well-known/agent-card.json")
        async def card() -> JSONResponse:
            return JSONResponse(
                content={
                    "agent_id": f"did:nexus:{self.agent_id}",
                    "name": "SDK Harness Mock Runtime",
                    "protocol_version": "1.0",
                    "endpoint": "http://sdk-harness-mock",
                    "capabilities": ["tasks/send", "tasks/sendSubscribe", "tasks/get"],
                }
            )

        @app.post("/rpc")
        async def rpc(request: Request) -> JSONResponse:
            body = await request.json()
            request_id = str(body.get("id") or "mock-req")
            method = str(body.get("method") or "")
            params = body.get("params") if isinstance(body.get("params"), dict) else {}

            auth = request.headers.get("Authorization", "")
            token = auth.split(" ", 1)[1] if auth.startswith("Bearer ") else None

            status_code, payload = self.issue_task(
                method=method,
                params=params,
                request_id=request_id,
                token=token,
            )
            return JSONResponse(status_code=status_code, content=payload)

        @app.get("/events/{task_id}")
        async def events(task_id: str, request: Request) -> StreamingResponse:
            auth = request.headers.get("Authorization", "")
            token = auth.split(" ", 1)[1] if auth.startswith("Bearer ") else None
            if not self._auth_ok(token):
                return StreamingResponse(iter(["event: nexus.task.error\ndata: {\"reason\": \"auth_failed\"}\n\n"]), status_code=401)
            return StreamingResponse(self.sse_frames(task_id), media_type="text/event-stream")

        return app


class MockWebSocketConnection:
    """Minimal async-iterable websocket compatible object for harness tests."""

    def __init__(self, messages: list[str]) -> None:
        self._messages = list(messages)
        self._closed = False

    def __aiter__(self) -> MockWebSocketConnection:
        return self

    async def __anext__(self) -> str:
        if self._closed or not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)

    async def send(self, _data: Any) -> None:  # pragma: no cover - reserved for future use
        return None

    async def close(self) -> None:
        self._closed = True



def build_mock_ws_connect(runtime: MockNexusRuntime) -> Callable[..., Awaitable[MockWebSocketConnection]]:
    """Build an awaitable websocket connector used by WebSocketTransport tests."""

    async def _connect(url: str, *, extra_headers: dict[str, str] | None = None, **_: Any) -> MockWebSocketConnection:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        token_from_query = (query.get("token") or [None])[0]
        token = token_from_query

        if not token and extra_headers:
            auth = extra_headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth.split(" ", 1)[1]

        if not runtime._auth_ok(token):
            raise RuntimeError("websocket auth_failed")

        task_id = parsed.path.rsplit("/", 1)[-1]
        return MockWebSocketConnection(runtime.websocket_messages(task_id))

    return _connect
