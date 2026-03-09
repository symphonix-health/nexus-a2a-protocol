from __future__ import annotations

import pytest

from tests.sdk_harness.runner import close_context, create_context


@pytest.mark.asyncio
async def test_live_context_uses_explicit_rpc_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDK_HARNESS_MODE", "live")
    monkeypatch.setenv("NEXUS_ROUTER_URL", "http://localhost:9010")
    monkeypatch.setenv("NEXUS_ROUTER_RPC_URL", "http://localhost:9011/custom-rpc")
    monkeypatch.setenv("NEXUS_WS_URL_TEMPLATE", "ws://localhost:9010/ws/{task_id}?token={token}")
    monkeypatch.setenv("NEXUS_JWT_TOKEN", "token-live")

    context = await create_context()
    try:
        assert context.mode == "live"
        assert context.base_url == "http://localhost:9010"
        assert context.rpc_url == "http://localhost:9011/custom-rpc"
    finally:
        await close_context(context)


@pytest.mark.asyncio
async def test_live_context_defaults_rpc_url_from_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDK_HARNESS_MODE", "live")
    monkeypatch.setenv("NEXUS_ROUTER_URL", "http://localhost:9020")
    monkeypatch.delenv("NEXUS_ROUTER_RPC_URL", raising=False)
    monkeypatch.setenv("NEXUS_WS_URL_TEMPLATE", "ws://localhost:9020/ws/{task_id}?token={token}")
    monkeypatch.setenv("NEXUS_JWT_TOKEN", "token-live")

    context = await create_context()
    try:
        assert context.mode == "live"
        assert context.base_url == "http://localhost:9020"
        assert context.rpc_url == "http://localhost:9020/rpc"
    finally:
        await close_context(context)
