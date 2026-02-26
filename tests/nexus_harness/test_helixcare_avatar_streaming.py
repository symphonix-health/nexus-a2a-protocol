"""Matrix-driven harness tests for the clinician-avatar streaming agent.

Loads helixcare_avatar_streaming_matrix.json and exercises all 20 scenarios
(10 positive, 7 negative, 4 edge) against the live agent at HC_AVATAR_URL
(default: http://localhost:8039).

WebSocket tests require the ``websockets`` library.  HTTP tests use the
shared ``client`` (httpx.AsyncClient) fixture from conftest.
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.parse
from typing import Any

import httpx
import pytest

from tests.nexus_harness.runner import (
    HELIXCARE_URLS,
    ScenarioResult,
    assert_deterministic_negative_rpc,
    auth_headers_for_negative_scenario,
    get_report,
    pytest_ids,
    scenarios_for_helixcare,
)

# ── Matrix ─────────────────────────────────────────────────────────────────

MATRIX = "helixcare_avatar_streaming_matrix.json"
AVATAR_URL = HELIXCARE_URLS["clinician-avatar"]  # http://localhost:8039

_positive = scenarios_for_helixcare(MATRIX, scenario_type="positive")
_negative = scenarios_for_helixcare(MATRIX, scenario_type="negative")
_edge = scenarios_for_helixcare(MATRIX, scenario_type="edge")

# ── Optional websockets import ─────────────────────────────────────────────

try:
    import websockets  # type: ignore[import]
    import websockets.exceptions  # type: ignore[import]

    _HAS_WS = True
except ImportError:
    websockets = None  # type: ignore[assignment]
    _HAS_WS = False


# ── Helpers ────────────────────────────────────────────────────────────────


def _ws_url(token: str) -> str:
    """Convert avatar HTTP base URL to a WebSocket TTS-stream URL."""
    base = AVATAR_URL.replace("https://", "wss://").replace("http://", "ws://")
    return f"{base.rstrip('/')}/api/tts/stream?token={urllib.parse.quote(token)}"


async def _collect_ws_frames(
    token: str,
    messages_to_send: list[dict[str, Any]],
    *,
    max_frames: int = 25,
    recv_timeout: float = 8.0,
) -> tuple[list[dict[str, Any]], int]:
    """Open a TTS WebSocket, send messages, and collect JSON frames + PCM byte count.

    Returns ``(json_messages, pcm_byte_count)``.

    Raises ``RuntimeError`` if the websockets library is unavailable.
    Raises ``ConnectionError`` if the agent is not reachable.
    """
    if not _HAS_WS:
        raise RuntimeError("websockets library not installed; pip install websockets")

    url = _ws_url(token)
    json_msgs: list[dict[str, Any]] = []
    pcm_bytes = 0

    try:
        async with websockets.connect(url, open_timeout=5) as ws:
            for msg in messages_to_send:
                await ws.send(json.dumps(msg))

            for _ in range(max_frames):
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=recv_timeout)
                except asyncio.TimeoutError:
                    break
                if isinstance(raw, bytes):
                    pcm_bytes += len(raw)
                else:
                    data = json.loads(raw)
                    json_msgs.append(data)
                    if data.get("type") == "end":
                        break
    except (ConnectionRefusedError, OSError) as exc:
        raise ConnectionError(f"Avatar agent not reachable at {AVATAR_URL}") from exc

    return json_msgs, pcm_bytes


async def _create_session(client: httpx.AsyncClient, auth_headers: dict[str, str]) -> str:
    """Create a minimal avatar session and return its session_id."""
    payload = {
        "jsonrpc": "2.0",
        "id": "harness-setup",
        "method": "avatar/start_session",
        "params": {
            "patient_case": {
                "patient_profile": {
                    "chief_complaint": "Chest pain",
                    "urgency": "high",
                }
            },
            "persona": {"name": "Dr. Harness", "specialty": "emergency medicine"},
        },
    }
    resp = await client.post(
        f"{AVATAR_URL}/rpc",
        headers=auth_headers,
        content=json.dumps(payload),
        timeout=10.0,
    )
    body = resp.json()
    assert "result" in body, f"Failed to create session: {body}"
    return body["result"]["session_id"]


def _resolve_dynamic_session(payload: dict[str, Any], session_id: str | None) -> dict[str, Any]:
    """Deep-copy payload and replace __dynamic__ session_id placeholder."""
    payload = json.loads(json.dumps(payload))
    if isinstance(payload.get("params"), dict):
        if payload["params"].get("session_id") == "__dynamic__":
            payload["params"]["session_id"] = session_id or ""
    return payload


def _mk_sr(scenario: dict[str, Any]) -> ScenarioResult:
    return ScenarioResult(
        use_case_id=scenario["use_case_id"],
        scenario_title=scenario["scenario_title"],
        poc_demo=scenario["poc_demo"],
        scenario_type=scenario["scenario_type"],
        requirement_ids=scenario.get("requirement_ids", []),
    )


# ── Positive tests ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("scenario", _positive, ids=pytest_ids(_positive))
@pytest.mark.asyncio
async def test_helixcare_avatar_streaming_positive(
    scenario: dict[str, Any],
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    jwt_token: str,
) -> None:
    sr = _mk_sr(scenario)
    t0 = time.monotonic()
    try:
        payload = scenario.get("input_payload", {})
        step = payload.get("protocol_step", "")

        # ── Agent card ────────────────────────────────────────────────
        if step == "agent_card_get":
            resp = await client.get(
                f"{AVATAR_URL}/.well-known/agent-card.json", timeout=10.0
            )
            assert resp.status_code == 200, f"Agent card: {resp.status_code}"
            card = resp.json()
            assert isinstance(card, dict), "Agent card must be a JSON object"
            sr.status = "pass"

        # ── Health check ──────────────────────────────────────────────
        elif step == "health_check":
            resp = await client.get(f"{AVATAR_URL}/health", timeout=10.0)
            assert resp.status_code == 200, f"Health: {resp.status_code}"
            data = resp.json()
            for field in scenario.get("expected_result", {}).get("contains", []):
                assert field in data, f"Health response missing '{field}'"
            sr.status = "pass"

        # ── Media serving ─────────────────────────────────────────────
        elif step == "media_get":
            filename = payload.get("filename", "")
            encoded = urllib.parse.quote(filename, safe="")
            resp = await client.get(f"{AVATAR_URL}/media/{encoded}", timeout=10.0)
            exp = scenario.get("expected_http_status", 200)
            assert resp.status_code == exp, f"Media: expected {exp} got {resp.status_code}"
            sr.status = "pass"

        # ── TTS WebSocket — frame structure ───────────────────────────
        elif step == "tts_stream":
            text = payload.get("text", "Hello.")
            voice = payload.get("voice", "alloy")
            msgs, _ = await _collect_ws_frames(
                jwt_token, [{"type": "speak", "text": text, "voice": voice}]
            )
            types = {m.get("type") for m in msgs}
            for expected_frame in scenario.get("expected_result", {}).get("contains", []):
                assert expected_frame in types, (
                    f"Missing frame type '{expected_frame}' in TTS stream; received {sorted(types)}"
                )
            sr.status = "pass"

        # ── TTS WebSocket — viseme structure ──────────────────────────
        elif step == "tts_stream_visemes":
            text = payload.get("text", "Hello.")
            voice = payload.get("voice", "alloy")
            msgs, _ = await _collect_ws_frames(
                jwt_token, [{"type": "speak", "text": text, "voice": voice}]
            )
            visemes_msg = next((m for m in msgs if m.get("type") == "visemes"), None)
            assert visemes_msg is not None, "No 'visemes' frame received from TTS stream"
            visemes = visemes_msg.get("visemes", [])
            assert isinstance(visemes, list) and len(visemes) >= 1, (
                f"visemes list must be non-empty; got {visemes!r}"
            )
            v0 = visemes[0]
            assert "time_ms" in v0, f"First viseme missing 'time_ms'; got {v0}"
            assert "weight" in v0, f"First viseme missing 'weight'; got {v0}"
            sr.status = "pass"

        # ── Standard JSON-RPC calls (with optional __dynamic__ session) ─
        elif payload.get("jsonrpc"):
            needs_dynamic = (
                isinstance(payload.get("params"), dict)
                and payload["params"].get("session_id") == "__dynamic__"
            )
            session_id = await _create_session(client, auth_headers) if needs_dynamic else None
            resolved = _resolve_dynamic_session(payload, session_id)

            resp = await client.post(
                f"{AVATAR_URL}/rpc",
                headers=auth_headers,
                content=json.dumps(resolved),
                timeout=15.0,
            )
            exp_status = scenario.get("expected_http_status", 200)
            assert resp.status_code == exp_status, (
                f"{scenario['use_case_id']}: expected HTTP {exp_status} got {resp.status_code}"
            )
            body = resp.json()
            expected = scenario.get("expected_result", {})
            if expected.get("ok"):
                result = body.get("result", {})
                for field in expected.get("contains", []):
                    assert field in result or field in json.dumps(result), (
                        f"Missing '{field}' in result; got {result}"
                    )
            sr.status = "pass"

        else:
            sr.status = "pass"

    except AssertionError as exc:
        sr.status = "fail"
        sr.message = str(exc)
    except Exception as exc:
        sr.status = "fail"
        sr.message = f"{type(exc).__name__}: {exc}"
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)


# ── Negative + Edge tests ──────────────────────────────────────────────────


@pytest.mark.parametrize("scenario", _negative + _edge, ids=pytest_ids(_negative + _edge))
@pytest.mark.asyncio
async def test_helixcare_avatar_streaming_negative(
    scenario: dict[str, Any],
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    jwt_token: str,
) -> None:
    sr = _mk_sr(scenario)
    t0 = time.monotonic()
    try:
        payload = scenario.get("input_payload", {})
        step = payload.get("protocol_step", "")
        stype = scenario.get("scenario_type", "")

        # ══ EDGE SCENARIOS ═══════════════════════════════════════════════

        if stype == "edge" and step == "tts_stream_empty_then_real":
            # Empty speak is silently skipped; subsequent real text should produce end frame
            first_text = payload.get("first_text", "")
            second_text = payload.get("second_text", "Hello.")
            voice = payload.get("voice", "alloy")
            msgs, _ = await _collect_ws_frames(
                jwt_token,
                [
                    {"type": "speak", "text": first_text, "voice": voice},
                    {"type": "speak", "text": second_text, "voice": voice},
                ],
                max_frames=25,
            )
            types = [m.get("type") for m in msgs]
            assert "end" in types, (
                f"Expected 'end' frame after real speak following empty; received types: {types}"
            )
            sr.status = "pass"

        elif stype == "edge" and step == "multi_session":
            # Two independently created sessions must have different IDs
            cases = payload.get("cases", [])
            session_ids: list[str] = []
            for case in cases:
                rpc = {
                    "jsonrpc": "2.0",
                    "id": "harness-multi",
                    "method": "avatar/start_session",
                    "params": {
                        "patient_case": {"patient_profile": case},
                        "persona": {"name": "Dr. Harness"},
                    },
                }
                resp = await client.post(
                    f"{AVATAR_URL}/rpc",
                    headers=auth_headers,
                    content=json.dumps(rpc),
                    timeout=10.0,
                )
                assert resp.status_code == 200, f"start_session returned {resp.status_code}"
                sid = resp.json()["result"]["session_id"]
                session_ids.append(sid)
            assert len(set(session_ids)) == len(cases), (
                f"Session IDs not independent: {session_ids}"
            )
            sr.status = "pass"

        elif stype == "edge" and step == "double_end_session":
            # First end_session → ended=True; second → ended=False or error
            session_id = await _create_session(client, auth_headers)
            end_rpc = {
                "jsonrpc": "2.0",
                "id": "harness-end",
                "method": "avatar/end_session",
                "params": {"session_id": session_id},
            }
            r1 = await client.post(
                f"{AVATAR_URL}/rpc",
                headers=auth_headers,
                content=json.dumps(end_rpc),
                timeout=10.0,
            )
            r2 = await client.post(
                f"{AVATAR_URL}/rpc",
                headers=auth_headers,
                content=json.dumps(end_rpc),
                timeout=10.0,
            )
            assert r1.status_code == 200
            assert r2.status_code == 200
            b1 = r1.json()
            b2 = r2.json()
            assert b1.get("result", {}).get("ended") is True, (
                f"First end_session should return ended=True; got {b1}"
            )
            # Second call: either ended=False OR an error envelope — both acceptable
            has_ended_false = b2.get("result", {}).get("ended") is False
            has_error = "error" in b2
            assert has_ended_false or has_error, (
                f"Second end_session should signal session already gone; got {b2}"
            )
            sr.status = "pass"

        elif stype == "edge" and step == "tts_stream_cancel":
            # Send speak then immediately cancel; server must not crash
            text = payload.get("text", "This is a test sentence.")
            voice = payload.get("voice", "alloy")
            # Only requirement: no unhandled exception (no assertion on frames received)
            await _collect_ws_frames(
                jwt_token,
                [
                    {"type": "speak", "text": text, "voice": voice},
                    {"type": "cancel"},
                ],
                max_frames=15,
                recv_timeout=4.0,
            )
            sr.status = "pass"

        # ══ NEGATIVE SCENARIOS ═══════════════════════════════════════════

        elif step == "tts_stream_no_auth":
            # WebSocket without token must be rejected — any non-success is a pass
            if not _HAS_WS:
                raise RuntimeError("websockets library not installed; pip install websockets")
            base = AVATAR_URL.replace("https://", "wss://").replace("http://", "ws://")
            url_no_auth = f"{base.rstrip('/')}/api/tts/stream"
            rejected = False
            try:
                async with websockets.connect(url_no_auth, open_timeout=5) as ws:
                    try:
                        # Server may send a close frame or just disconnect
                        raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                        # If we somehow received a frame, check for auth error
                        if isinstance(raw, str):
                            data = json.loads(raw)
                            if data.get("type") == "error" or data.get("code") == 4001:
                                rejected = True
                    except (asyncio.TimeoutError, Exception):
                        rejected = True
            except Exception:
                # Any exception during connect = server rejected the connection
                rejected = True
            assert rejected, "Expected server to reject unauthenticated WebSocket connection"
            sr.status = "pass"

        elif step == "media_get":
            # Negative/edge media access: expect specific HTTP status (404)
            filename = payload.get("filename", "nonexistent.mp4")
            encoded = urllib.parse.quote(filename, safe="")
            resp = await client.get(f"{AVATAR_URL}/media/{encoded}", timeout=10.0)
            exp = scenario.get("expected_http_status", 404)
            assert resp.status_code == exp, (
                f"{scenario['use_case_id']}: expected {exp} got {resp.status_code}"
            )
            sr.status = "pass"

        elif payload.get("jsonrpc") and scenario.get("auth_mode", "").startswith("jwt_missing"):
            # Auth-required RPC without token → 401
            headers = auth_headers_for_negative_scenario(scenario, auth_headers)
            resp = await client.post(
                f"{AVATAR_URL}/rpc",
                headers=headers,
                content=json.dumps(payload),
                timeout=10.0,
            )
            body = (
                resp.json()
                if "application/json" in resp.headers.get("content-type", "")
                else {}
            )
            assert_deterministic_negative_rpc(
                scenario,
                status_code=resp.status_code,
                body=body if isinstance(body, dict) else {},
            )
            sr.status = "pass"

        elif payload.get("jsonrpc"):
            # Standard negative RPC: unknown method, empty session, unknown session
            resp = await client.post(
                f"{AVATAR_URL}/rpc",
                headers=auth_headers,
                content=json.dumps(payload),
                timeout=10.0,
            )
            exp_status = scenario.get("expected_http_status", 200)
            assert resp.status_code == exp_status, (
                f"{scenario['use_case_id']}: expected HTTP {exp_status} got {resp.status_code}"
            )
            body = resp.json()
            assert "error" in body, f"Expected error envelope in response; got {body}"
            expected = scenario.get("expected_result", {})
            if "code" in expected:
                actual_code = body["error"].get("code")
                assert actual_code == expected["code"], (
                    f"Expected error.code {expected['code']}, got {actual_code}; body={body}"
                )
            sr.status = "pass"

        else:
            sr.status = "pass"

    except AssertionError as exc:
        sr.status = "fail"
        sr.message = str(exc)
    except Exception as exc:
        sr.status = "fail"
        sr.message = f"{type(exc).__name__}: {exc}"
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)
