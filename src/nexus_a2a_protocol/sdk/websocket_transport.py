"""WebSocket streaming transport with HTTP JSON-RPC task submission."""

from __future__ import annotations

import inspect
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any

import httpx
import websockets

from .client import nexus_rpc_call
from .transport import AgentTransport
from .types import (
    TaskEnvelope,
    TaskEvent,
    TaskSubmission,
    TransportError,
    extract_task_id_from_response,
    make_task_event,
)

WsConnectFn = Callable[..., Awaitable[Any]]


class WebSocketTransport(AgentTransport):
    """Send tasks over HTTP and stream lifecycle events via WebSocket."""

    def __init__(
        self,
        *,
        rpc_url: str,
        ws_url_template: str,
        token: str | None,
        timeout: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
        ws_connect: WsConnectFn | None = None,
        agent_id: str = "nexus-agent",
    ) -> None:
        self.rpc_url = rpc_url.rstrip("/")
        self.ws_url_template = ws_url_template
        self.token = token
        self.timeout = timeout
        self.agent_id = agent_id
        self._http_client = http_client
        self._owns_http_client = http_client is None
        self._ws_connect = ws_connect

    async def connect(self) -> None:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self.timeout)
            self._owns_http_client = True

    def _build_ws_url(self, task_id: str) -> str:
        return self.ws_url_template.format(task_id=task_id, token=self.token or "")

    async def _connect_ws(self, url: str, token_override: str | None = None) -> Any:
        headers = {}
        token = token_override or self.token
        if token:
            headers["Authorization"] = f"Bearer {token}"

        connector: Any = self._ws_connect or websockets.connect
        kwargs = {"extra_headers": headers} if headers else {}

        candidate = connector(url, **kwargs)
        if inspect.isawaitable(candidate):
            return await candidate
        return candidate

    async def send_task(self, task: TaskEnvelope | Mapping[str, Any]) -> TaskSubmission:
        if self._http_client is None:
            await self.connect()
        assert self._http_client is not None

        token_override = None
        token_provided = False
        if isinstance(task, Mapping) and "token" in task:
            token_provided = True
            maybe_token = task.get("token")
            if isinstance(maybe_token, str):
                token_override = maybe_token.strip() or None
            elif maybe_token is None:
                token_override = None

        envelope = TaskEnvelope.from_input(task)
        base_url = self.rpc_url
        if base_url.endswith("/rpc"):
            base_url = base_url[: -len("/rpc")]

        response = await nexus_rpc_call(
            base_url,
            envelope.method,
            envelope.params,
            token_override if token_provided else self.token,
            request_id=envelope.request_id,
            timeout=self.timeout,
            client=self._http_client,
        )
        task_id = extract_task_id_from_response(response)
        if not task_id:
            raise TransportError("RPC result missing task_id", details=response)

        status = "accepted"
        result = response.get("result")
        if isinstance(result, Mapping):
            state = result.get("status")
            if isinstance(state, Mapping):
                maybe_state = state.get("state")
                if isinstance(maybe_state, str) and maybe_state.strip():
                    status = maybe_state.strip()

        return TaskSubmission(task_id=task_id, status=status, raw_response=response)

    async def stream_events(self, task_id: str) -> AsyncIterator[TaskEvent]:
        url = self._build_ws_url(task_id)
        ws = await self._connect_ws(url)
        try:
            async for raw_message in ws:
                if isinstance(raw_message, (bytes, bytearray)):
                    raw_text = raw_message.decode("utf-8", errors="replace")
                else:
                    raw_text = str(raw_message)
                try:
                    payload = json.loads(raw_text)
                except json.JSONDecodeError as exc:
                    raise TransportError("Invalid websocket event payload", details=raw_text) from exc

                if not isinstance(payload, Mapping):
                    raise TransportError("Websocket event payload must be object", details=payload)

                event_type = str(payload.get("event") or payload.get("type") or "nexus.task.status")
                evt = make_task_event(
                    event_type=event_type,
                    payload=payload.get("data", payload.get("payload", {})),
                    task_id=str(payload.get("task_id") or task_id),
                    seq=payload.get("seq") if isinstance(payload.get("seq"), int) else None,
                    agent_id=self.agent_id,
                    event_id=str(payload.get("event_id") or "") or None,
                    timestamp=str(payload.get("timestamp") or "") or None,
                )
                yield evt
                if evt.is_terminal:
                    return
        finally:
            close = getattr(ws, "close", None)
            if callable(close):
                maybe = close()
                if inspect.isawaitable(maybe):
                    await maybe

    async def stop(self) -> None:
        if self._owns_http_client and self._http_client is not None:
            await self._http_client.aclose()
        self._http_client = None
