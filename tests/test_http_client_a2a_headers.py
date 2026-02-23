from __future__ import annotations

import pytest
import httpx

from shared.nexus_common import http_client


@pytest.mark.asyncio
async def test_jsonrpc_call_sends_a2a_and_trace_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["content_type"] = request.headers.get("Content-Type", "")
        observed["accept"] = request.headers.get("Accept", "")
        observed["a2a_version"] = request.headers.get("A2A-Version", "")
        observed["a2a_extensions"] = request.headers.get("A2A-Extensions", "")
        observed["traceparent"] = request.headers.get("traceparent", "")
        observed["tracestate"] = request.headers.get("tracestate", "")
        observed["trace_id"] = request.headers.get("X-Nexus-Trace-Id", "")
        return httpx.Response(
            status_code=200,
            json={"jsonrpc": "2.0", "id": "req-1", "result": {"ok": True}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(http_client, "_get_client", lambda timeout: client)

    response = await http_client.jsonrpc_call(
        "http://unit-test/rpc",
        token="token-123",
        method="tasks/send",
        params={"task": {"id": "task-1"}},
        id_="req-1",
        correlation={
            "trace_id": "trace-123",
            "traceparent": "00-11111111111111111111111111111111-2222222222222222-01",
            "tracestate": "vendor=test",
        },
    )
    await client.aclose()

    assert response.get("result", {}).get("ok") is True
    assert observed["content_type"] == "application/a2a+json"
    assert observed["accept"] == "application/a2a+json"
    assert observed["a2a_version"] == "1.0"
    assert bool(observed["a2a_extensions"])
    assert observed["traceparent"] == "00-11111111111111111111111111111111-2222222222222222-01"
    assert observed["tracestate"] == "vendor=test"
    assert observed["trace_id"] == "trace-123"
