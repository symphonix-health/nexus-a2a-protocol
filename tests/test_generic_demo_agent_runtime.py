from __future__ import annotations

import asyncio
import copy
import json
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = Path(__file__).resolve().parents[1]
shared_path = str(REPO_ROOT / "shared")
if shared_path not in sys.path:
    sys.path.insert(0, shared_path)

from nexus_common.auth import mint_jwt  # noqa: E402
from nexus_common.generic_demo_agent import build_generic_demo_app  # noqa: E402

JWT_SECRET = "unit-test-secret"
REQUIRED_SCOPE = "nexus:invoke"


@pytest.fixture
def auth_token() -> str:
    return mint_jwt(
        "unit-test",
        JWT_SECRET,
        ttl_seconds=3600,
        scope=REQUIRED_SCOPE,
    )


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("NEXUS_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("NEXUS_REQUIRED_SCOPE", REQUIRED_SCOPE)
    monkeypatch.setenv("NEXUS_IDEMPOTENCY_BACKEND", "memory")
    card = {
        "name": "unit-generic-agent",
        "protocol": "NEXUS-A2A",
        "protocolVersion": "1.0",
        "methods": [
            "tasks/send",
            "tasks/sendSubscribe",
            "tasks/get",
            "tasks/cancel",
            "tasks/resubscribe",
        ],
        "capabilities": {"streaming": True, "websocket": True},
    }
    (tmp_path / "agent_card.json").write_text(json.dumps(card), encoding="utf-8")
    return build_generic_demo_app(default_name="unit-generic-agent", app_dir=str(tmp_path))


@pytest.fixture
async def client(app: object) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test-agent") as c:
        yield c


async def _rpc(client: AsyncClient, token: str, payload: dict) -> dict:
    resp = await client.post(
        "/rpc",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    assert resp.status_code == 200
    return resp.json()


@pytest.mark.asyncio
async def test_send_subscribe_duplicate_idempotency_reuses_cached_response(
    client: AsyncClient,
    auth_token: str,
) -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "tasks/sendSubscribe",
        "params": {
            "task": {"chief_complaint": "cough"},
            "idempotency": {
                "idempotency_key": "idem-1",
                "scope": "tenant-a:tasks/sendSubscribe",
                "dedup_window_ms": 60000,
                "payload_hash": "hash-a",
            },
        },
    }
    first = await _rpc(client, auth_token, payload)
    second_payload = copy.deepcopy(payload)
    second_payload["id"] = "req-2"
    second = await _rpc(client, auth_token, second_payload)

    assert "result" in first
    assert "result" in second
    assert second["result"]["task_id"] == first["result"]["task_id"]
    dedup = second["result"].get("dedup", {})
    assert dedup.get("duplicate") is True
    assert dedup.get("scope") == "tenant-a:tasks/sendSubscribe"


@pytest.mark.asyncio
async def test_duplicate_payload_hash_mismatch_is_reported(
    client: AsyncClient,
    auth_token: str,
) -> None:
    base = {
        "jsonrpc": "2.0",
        "id": "req-10",
        "method": "tasks/send",
        "params": {
            "task": {"chief_complaint": "headache"},
            "idempotency": {
                "idempotency_key": "idem-hash",
                "scope": "tenant-a:tasks/send",
                "dedup_window_ms": 60000,
                "payload_hash": "payload-v1",
            },
        },
    }
    _ = await _rpc(client, auth_token, base)

    mismatch = copy.deepcopy(base)
    mismatch["id"] = "req-11"
    mismatch["params"]["idempotency"]["payload_hash"] = "payload-v2"
    second = await _rpc(client, auth_token, mismatch)

    assert "result" in second
    dedup = second["result"].get("dedup", {})
    assert dedup.get("duplicate") is True
    assert dedup.get("payload_mismatch") is True


@pytest.mark.asyncio
async def test_tasks_resubscribe_replays_events_after_cursor(
    client: AsyncClient,
    auth_token: str,
) -> None:
    send = {
        "jsonrpc": "2.0",
        "id": "req-r1",
        "method": "tasks/sendSubscribe",
        "params": {"task": {"chief_complaint": "chest pain"}},
    }
    send_resp = await _rpc(client, auth_token, send)
    assert "result" in send_resp
    cursor = send_resp["result"].get("resume_cursor")
    assert isinstance(cursor, str) and cursor

    replay_resp: dict | None = None
    for _ in range(15):
        replay_req = {
            "jsonrpc": "2.0",
            "id": "req-r2",
            "method": "tasks/resubscribe",
            "params": {"cursor": cursor, "max_catchup_events": 100},
        }
        replay_resp = await _rpc(client, auth_token, replay_req)
        assert "result" in replay_resp
        if int(replay_resp["result"].get("replayed_count", 0)) > 0:
            break
        await asyncio.sleep(0.05)

    assert replay_resp is not None
    assert replay_resp["result"]["task_id"] == send_resp["result"]["task_id"]
    assert int(replay_resp["result"]["replayed_count"]) > 0
    assert isinstance(replay_resp["result"].get("resume_cursor"), str)
    events = replay_resp["result"].get("replayed_events", [])
    assert isinstance(events, list)
    assert events[0].get("stream", {}).get("stream_id") == send_resp["result"]["task_id"]


@pytest.mark.asyncio
async def test_tasks_resubscribe_invalid_cursor_returns_error(
    client: AsyncClient,
    auth_token: str,
) -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": "req-bad-cursor",
        "method": "tasks/resubscribe",
        "params": {"cursor": "not-a-valid-cursor"},
    }
    response = await _rpc(client, auth_token, payload)
    assert "error" in response
    assert response["error"]["code"] == -32002


@pytest.mark.asyncio
async def test_agent_card_parent_fallback_path_loads_card(
    tmp_path: Path,
    auth_token: str,
) -> None:
    parent_card = {
        "name": "parent-card-agent",
        "protocol": "NEXUS-A2A",
        "protocolVersion": "1.0",
        "methods": ["tasks/sendSubscribe"],
    }
    app_dir = tmp_path / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "agent_card.json").write_text(json.dumps(parent_card), encoding="utf-8")

    app = build_generic_demo_app(default_name="fallback-agent", app_dir=str(app_dir))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test-agent") as c:
        resp = await c.get("/.well-known/agent-card.json")
        assert resp.status_code == 200
        card = resp.json()
        assert card.get("name") == "parent-card-agent"
        assert "x-nexus-backpressure" in card
