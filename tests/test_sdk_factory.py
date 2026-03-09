from __future__ import annotations

import os

import pytest

from nexus_a2a_protocol.sdk import (
    HttpSseTransport,
    SimulationTransport,
    TransportError,
    TransportFactory,
    WebSocketTransport,
)


def test_factory_defaults_to_simulation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_TRANSPORT", raising=False)
    transport = TransportFactory.from_env()
    assert isinstance(transport, SimulationTransport)


def test_factory_http_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_TRANSPORT", "http_sse")
    monkeypatch.setenv("NEXUS_JWT_TOKEN", "token")
    monkeypatch.setenv("NEXUS_ROUTER_URL", "http://localhost:9000")
    transport = TransportFactory.from_env()
    assert isinstance(transport, HttpSseTransport)


def test_factory_websocket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_TRANSPORT", "websocket")
    monkeypatch.setenv("NEXUS_JWT_TOKEN", "token")
    monkeypatch.setenv("NEXUS_ROUTER_RPC_URL", "http://localhost:9000/rpc")
    monkeypatch.setenv("NEXUS_WS_URL_TEMPLATE", "ws://localhost:9000/ws/{task_id}?token={token}")
    transport = TransportFactory.from_env()
    assert isinstance(transport, WebSocketTransport)


def test_factory_rejects_unsupported_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_TRANSPORT", "unsupported")
    with pytest.raises(TransportError):
        TransportFactory.from_env()


def test_factory_uses_explicit_mode_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_TRANSPORT", "websocket")
    monkeypatch.setenv("NEXUS_JWT_TOKEN", "token")
    transport = TransportFactory.from_env(mode="simulation")
    assert isinstance(transport, SimulationTransport)
