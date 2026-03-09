"""HTTP+SSE transport adapter for Nexus runtime integration."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any

import httpx

from .client import consume_sse_stream, nexus_rpc_call
from .transport import AgentTransport
from .types import (
    TaskEnvelope,
    TaskEvent,
    TaskSubmission,
    TransportError,
    extract_task_id_from_response,
)


class HttpSseTransport(AgentTransport):
    """Submit tasks via HTTP JSON-RPC and stream lifecycle over SSE."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
        agent_id: str = "nexus-agent",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.agent_id = agent_id
        self._client = client
        self._owns_client = client is None

    async def connect(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
            self._owns_client = True

    async def send_task(self, task: TaskEnvelope | Mapping[str, Any]) -> TaskSubmission:
        if self._client is None:
            await self.connect()
        assert self._client is not None

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
        response = await nexus_rpc_call(
            self.base_url,
            envelope.method,
            envelope.params,
            token_override if token_provided else self.token,
            request_id=envelope.request_id,
            timeout=self.timeout,
            client=self._client,
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
        if self._client is None:
            await self.connect()
        assert self._client is not None

        async for evt in consume_sse_stream(
            self.base_url,
            task_id,
            self.token,
            timeout=self.timeout,
            client=self._client,
            agent_id=self.agent_id,
        ):
            yield evt

    async def stop(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
        self._client = None
