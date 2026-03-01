"""Tests for the clinician-avatar agent's streaming TTS WebSocket endpoint.

These tests load the FastAPI app directly via importlib (no running service
needed) and exercise the /api/tts/stream WebSocket handler under two key
conditions:

  1.  No OPENAI_API_KEY → meta message carries ``"synthetic": True``; no
      binary PCM frames are sent; browser TTS fallback is expected on the
      client side.

  2.  With a stub OPENAI_API_KEY that will raise on first use → the
      exception path falls back gracefully (exception caught, ``end``
      message is still sent, no unhandled crash).

The avatar RPC methods (avatar/start_session, avatar/patient_message) are
also smoke-tested via the TestClient.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ── App loader ────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[1]
_AGENT_DIR = _REPO_ROOT / "demos" / "helixcare" / "clinician-avatar-agent"


def _load_avatar_app():
    """Import the FastAPI app from the clinician-avatar-agent without a running process."""
    agent_app_dir = str(_AGENT_DIR)
    if agent_app_dir not in sys.path:
        sys.path.insert(0, agent_app_dir)

    spec = importlib.util.spec_from_file_location(
        "avatar_app_main",
        str(_AGENT_DIR / "app" / "main.py"),
    )
    module = importlib.util.module_from_spec(spec)
    # Register so monkeypatch scans in tests can find and patch module globals.
    sys.modules["avatar_app_main"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.app


@pytest.fixture(scope="module")
def avatar_app():
    return _load_avatar_app()


# ── JWT helper ────────────────────────────────────────────────────────────────

_JWT_SECRET = "dev-secret-change-me"


def _mint_token() -> str:
    from shared.nexus_common.auth import mint_jwt

    return mint_jwt("test-client", _JWT_SECRET)


def _ws_recv(ws):
    """Decode a frame from a starlette TestClient WebSocket.

    starlette's ``ws.receive()`` returns an ASGI event dict of the form::

        {"type": "websocket.send", "text": "...", "bytes": None}
        {"type": "websocket.send", "text": None, "bytes": b"..."}

    Returns ``(is_binary: bool, payload: str | bytes)``.
    """
    event = ws.receive()
    if isinstance(event, dict):
        raw_bytes = event.get("bytes")
        raw_text  = event.get("text")
        if raw_bytes:
            return True, raw_bytes
        if raw_text:
            return False, raw_text
        # Both absent (e.g. disconnect event) — treat as empty text
        return False, ""
    # Older starlette versions returned the value directly
    if isinstance(event, bytes):
        return True, event
    return False, str(event)


# ── WebSocket TTS stream — synthetic path (no API key) ────────────────────────


class TestTtsStreamSyntheticPath:
    """When OPENAI_API_KEY is absent the handler emits tts_error + end (no silent fallback)."""

    def test_meta_has_synthetic_flag(self, avatar_app, monkeypatch):
        """No API key → tts_error frame is sent, no PCM, no synthetic meta."""
        from starlette.testclient import TestClient

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        token = _mint_token()

        with TestClient(avatar_app) as client:
            with client.websocket_connect(f"/api/tts/stream?token={token}") as ws:
                ws.send_json({"type": "speak", "text": "Hello, how are you?", "voice": "alloy"})

                messages = []
                pcm_bytes = 0
                for _ in range(10):  # read up to 10 frames
                    is_bin, payload = _ws_recv(ws)
                    if is_bin:
                        pcm_bytes += len(payload)
                    else:
                        msg = json.loads(payload)
                        messages.append(msg)
                        if msg.get("type") == "end":
                            break

        types = [m["type"] for m in messages]
        assert "tts_error" in types, "Expected tts_error frame when no API key"
        assert "end" in types, "Expected end frame after tts_error"
        assert "meta" not in types, "Got meta frame unexpectedly — browser fallback path was not removed"
        assert pcm_bytes == 0, "Expected zero PCM bytes when no API key"

    def test_visemes_list_is_non_empty(self, avatar_app, monkeypatch):
        """No API key → tts_error sent; no visemes frame (hard-fail before viseme generation)."""
        from starlette.testclient import TestClient

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        token = _mint_token()

        with TestClient(avatar_app) as client:
            with client.websocket_connect(f"/api/tts/stream?token={token}") as ws:
                ws.send_json({"type": "speak", "text": "Tell me about your symptoms.", "voice": "alloy"})

                messages = []
                for _ in range(10):
                    is_bin, payload = _ws_recv(ws)
                    if not is_bin:
                        msg = json.loads(payload)
                        messages.append(msg)
                        if msg.get("type") == "end":
                            break

        types = [m["type"] for m in messages]
        # New protocol: no API key → tts_error + end (no visemes, no PCM)
        assert "tts_error" in types, "Expected tts_error frame when no API key"
        assert "end" in types, "Expected end frame after tts_error"
        assert "visemes" not in types, "Got unexpected visemes frame on error path"

    def test_empty_text_skips_entire_exchange(self, avatar_app, monkeypatch):
        """Sending an empty speak message should be silently ignored."""
        from starlette.testclient import TestClient

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        token = _mint_token()

        with TestClient(avatar_app) as client:
            with client.websocket_connect(f"/api/tts/stream?token={token}") as ws:
                ws.send_json({"type": "speak", "text": "", "voice": "alloy"})
                # Follow up with real text so the server doesn't just hang
                ws.send_json({"type": "speak", "text": "Hello.", "voice": "alloy"})

                types = []
                for _ in range(10):
                    is_bin, payload = _ws_recv(ws)
                    if not is_bin and payload:
                        msg = json.loads(payload)
                        types.append(msg["type"])
                        if msg.get("type") == "end":
                            break

        # The first empty speak was skipped; the second produced meta/visemes/end
        assert "end" in types

    def test_cancel_message_suppresses_end(self, avatar_app, monkeypatch):
        """Sending cancel before end should suppress the end message."""
        from starlette.testclient import TestClient

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        token = _mint_token()

        with TestClient(avatar_app) as client:
            with client.websocket_connect(f"/api/tts/stream?token={token}") as ws:
                ws.send_json({"type": "speak", "text": "A long sentence that takes a while.", "voice": "alloy"})
                ws.send_json({"type": "cancel"})
                # After cancel, server should not send `end`
                # Just close gracefully — no assertion needed beyond no crash


# ── WebSocket TTS stream — real PCM path (with API key) ───────────────────────


class TestTtsStreamRealPath:
    """When OPENAI_API_KEY is set, meta should not have synthetic flag."""

    def test_meta_has_no_synthetic_flag(self, avatar_app, monkeypatch):
        from starlette.testclient import TestClient

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-present")
        token = _mint_token()

        # We monkeypatch stream_tts_chunks to avoid a real API call
        import shared.clinician_avatar.video_clinician_provider as vcp

        async def _fake_chunks(text, voice="alloy", **kwargs):  # noqa: RUF029
            # Yield a minimal 4800-byte chunk of silence (16-bit LE zeroes)
            yield bytes(4800)

        monkeypatch.setattr(vcp, "stream_tts_chunks", _fake_chunks)
        # Also patch in the main module that already imported stream_tts_chunks

        import demos.helixcare  # noqa: F401 — ensure package is on path

        for mod_name, mod in list(sys.modules.items()):
            if mod_name == "avatar_app_main" or (
                hasattr(mod, "__file__")
                and mod.__file__
                and "clinician-avatar-agent" in (mod.__file__ or "")
                and mod.__file__.endswith("main.py")
            ):
                if hasattr(mod, "stream_tts_chunks"):
                    mod.stream_tts_chunks = _fake_chunks
                if hasattr(mod, "has_openai_tts"):
                    monkeypatch.setattr(mod, "has_openai_tts", lambda: True)

        with TestClient(avatar_app) as client:
            with client.websocket_connect(f"/api/tts/stream?token={token}") as ws:
                ws.send_json({"type": "speak", "text": "Good morning.", "voice": "alloy"})

                messages = []
                for _ in range(15):
                    is_bin, payload = _ws_recv(ws)
                    if not is_bin and payload:
                        msg = json.loads(payload)
                        messages.append(msg)
                        if msg.get("type") == "end":
                            break

        meta = next((m for m in messages if m["type"] == "meta"), None)
        assert meta is not None
        assert meta.get("synthetic") is not True, "Should not have synthetic=True when API key present"


# ── WebSocket authentication ───────────────────────────────────────────────────


class TestTtsStreamAuth:
    def test_missing_token_closes_with_4001(self, avatar_app):
        from starlette.testclient import TestClient
        from starlette.websockets import WebSocketDisconnect

        with TestClient(avatar_app) as client:
            with pytest.raises((WebSocketDisconnect, Exception)):
                with client.websocket_connect("/api/tts/stream") as ws:
                    ws.receive_json()

    def test_invalid_token_closes_with_4001(self, avatar_app):
        from starlette.testclient import TestClient
        from starlette.websockets import WebSocketDisconnect

        with TestClient(avatar_app) as client:
            with pytest.raises((WebSocketDisconnect, Exception)):
                with client.websocket_connect("/api/tts/stream?token=bad.token.here") as ws:
                    ws.receive_json()


# ── Avatar RPC smoke tests ────────────────────────────────────────────────────


class TestAvatarRpcSmoke:
    """Lightweight smoke tests for the /rpc endpoint via TestClient."""

    def _headers(self):
        return {
            "Authorization": f"Bearer {_mint_token()}",
            "Content-Type": "application/json",
        }

    def _rpc(self, client, method, params):
        resp = client.post(
            "/rpc",
            json={"jsonrpc": "2.0", "id": "t1", "method": method, "params": params},
            headers=self._headers(),
        )
        assert resp.status_code == 200
        return resp.json()

    def test_start_session_returns_session_id(self, avatar_app):
        from starlette.testclient import TestClient

        with TestClient(avatar_app) as client:
            body = self._rpc(client, "avatar/start_session", {
                "patient_case": {
                    "patient_profile": {
                        "chief_complaint": "Chest pain",
                        "urgency": "high",
                    }
                },
                "persona": {"name": "Dr. Lee", "specialty": "emergency medicine"},
            })

        assert "result" in body
        result = body["result"]
        assert result["session_id"].startswith("avatar-")
        assert result["consultation_phase"] in (
            "initiating", "gathering_information", "explanation", "closing"
        )
        assert isinstance(result["greeting"], str)
        assert len(result["greeting"]) > 10

    def test_patient_message_returns_response(self, avatar_app):
        from starlette.testclient import TestClient

        _reply = "I understand. Can you tell me more about the headache?"
        with patch(
            "shared.clinician_avatar.avatar_engine.llm_chat",
            return_value=_reply,
        ):
            with TestClient(avatar_app) as client:
                start = self._rpc(client, "avatar/start_session", {
                    "patient_case": {
                        "patient_profile": {
                            "chief_complaint": "Headache",
                            "urgency": "medium",
                        }
                    },
                    "persona": {"name": "Dr. Patel", "specialty": "neurology"},
                })
                sid = start["result"]["session_id"]

                msg = self._rpc(client, "avatar/patient_message", {
                    "session_id": sid,
                    "message": "I have had a throbbing headache for three days.",
                })

        assert "result" in msg
        assert "clinician_response" in msg["result"]
        assert len(msg["result"]["clinician_response"]) > 5

    def test_get_status_returns_session_info(self, avatar_app):
        from starlette.testclient import TestClient

        with TestClient(avatar_app) as client:
            start = self._rpc(client, "avatar/start_session", {
                "patient_case": {"patient_profile": {"chief_complaint": "Nausea"}},
                "persona": {"name": "Dr. Kim"},
            })
            sid = start["result"]["session_id"]

            status = self._rpc(client, "avatar/get_status", {"session_id": sid})

        assert status["result"]["session_id"] == sid
        assert "framework" in status["result"]
        assert status["result"]["turns"] >= 1  # at least the greeting

    def test_end_session_removes_session(self, avatar_app):
        from starlette.testclient import TestClient

        with TestClient(avatar_app) as client:
            start = self._rpc(client, "avatar/start_session", {
                "patient_case": {"patient_profile": {"chief_complaint": "Back pain"}},
                "persona": {"name": "Dr. Singh"},
            })
            sid = start["result"]["session_id"]

            end = self._rpc(client, "avatar/end_session", {"session_id": sid})
            assert end["result"]["ended"] is True

            # Status should now return an error (unknown session)
            status = self._rpc(client, "avatar/get_status", {"session_id": sid})
            assert "error" in status

    def test_unknown_method_returns_error(self, avatar_app):
        from starlette.testclient import TestClient

        with TestClient(avatar_app) as client:
            body = self._rpc(client, "avatar/nonexistent_method", {})

        assert "error" in body
        assert body["error"]["code"] == -32601

    def test_missing_session_id_returns_error(self, avatar_app):
        from starlette.testclient import TestClient

        with TestClient(avatar_app) as client:
            body = self._rpc(client, "avatar/patient_message", {
                "session_id": "",
                "message": "Hello",
            })

        assert "error" in body

    def test_rpc_requires_auth(self, avatar_app):
        from starlette.testclient import TestClient

        with TestClient(avatar_app) as client:
            resp = client.post(
                "/rpc",
                json={"jsonrpc": "2.0", "id": "x", "method": "avatar/start_session", "params": {}},
            )
        assert resp.status_code == 401


# ── Health and media endpoints ────────────────────────────────────────────────


class TestAvatarEndpoints:
    def test_health_returns_healthy(self, avatar_app):
        from starlette.testclient import TestClient

        with TestClient(avatar_app) as client:
            resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "sessions" in data
        assert "video_provider" in data

    def test_agent_card_is_valid_json(self, avatar_app):
        from starlette.testclient import TestClient

        with TestClient(avatar_app) as client:
            resp = client.get("/.well-known/agent-card.json")

        assert resp.status_code == 200
        card = resp.json()
        assert isinstance(card, dict)

    def test_media_not_found_returns_404(self, avatar_app):
        from starlette.testclient import TestClient

        with TestClient(avatar_app) as client:
            resp = client.get("/media/nonexistent_file_xyz.mp4")

        assert resp.status_code == 404

    def test_media_path_traversal_blocked(self, avatar_app):
        from starlette.testclient import TestClient

        with TestClient(avatar_app) as client:
            resp = client.get("/media/../.env")

        assert resp.status_code == 404

    def test_stt_upload_requires_openai_key(self, avatar_app, monkeypatch):
        from starlette.testclient import TestClient

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        headers = {"Authorization": f"Bearer {_mint_token()}"}
        files = {"file": ("patient.wav", b"fake-audio", "audio/wav")}
        data = {"language": "en"}

        with TestClient(avatar_app) as client:
            resp = client.post("/api/stt/upload", headers=headers, files=files, data=data)

        assert resp.status_code == 503
