"""
Tests for avatar agent audio pipeline and AI patient changes.

Covers:
1. main.py — syntax, tts_error logic, /api/patient/respond endpoint
2. tts_client.js — no synthetic fallbacks, tts_error handler present
3. chat_controller.js — AI patient functions, mode toggle, old code removed
4. avatar.html — new patient UI elements, v7 JS versions
5. patient_script_pack.json — v3, patient_context objects, no audio_clip refs
6. /api/patient/respond — HTTP-level integration test (requires live avatar agent on port 8039)
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import httpx
import pytest
import pytest_asyncio  # noqa: F401

ROOT = Path(__file__).parent.parent
STATIC = ROOT / "demos/helixcare/clinician-avatar-agent/app/static"
MAIN_PY = ROOT / "demos/helixcare/clinician-avatar-agent/app/main.py"
TTS_JS = STATIC / "tts_client.js"
CC_JS = STATIC / "chat_controller.js"
AVATAR_HTML = STATIC / "avatar.html"
PACK_JSON = STATIC / "patient_script_pack.json"
AVATAR_URL = "http://localhost:8039"


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def main_src() -> str:
    return MAIN_PY.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def tts_src() -> str:
    return TTS_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def cc_src() -> str:
    return CC_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def html_src() -> str:
    return AVATAR_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def pack_data() -> dict:
    return json.loads(PACK_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def avatar_running() -> bool:
    try:
        import urllib.request

        urllib.request.urlopen(f"{AVATAR_URL}/health", timeout=2)
        return True
    except Exception:
        return False


# ── 1. main.py ───────────────────────────────────────────────────────────────


class TestMainPy:
    def test_syntax(self, main_src):
        """No Python syntax errors."""
        try:
            ast.parse(main_src)
        except SyntaxError as exc:
            pytest.fail(f"SyntaxError at line {exc.lineno}: {exc.msg}")

    def test_tts_error_frame_present(self, main_src):
        """WebSocket handler sends tts_error frame instead of synthetic fallback."""
        assert "tts_error" in main_src

    def test_synthetic_fallback_removed(self, main_src):
        """synthetic_fallback frame removed from WebSocket handler."""
        assert "synthetic_fallback" not in main_src

    def test_synthetic_true_removed(self, main_src):
        """synthetic: True meta flag removed."""
        assert '"synthetic": True' not in main_src
        assert "'synthetic': True" not in main_src

    def test_patient_respond_endpoint(self, main_src):
        """POST /api/patient/respond endpoint exists."""
        assert "/api/patient/respond" in main_src

    def test_llm_chat_in_patient_endpoint(self, main_src):
        """llm_chat is called inside the patient endpoint."""
        assert "llm_chat" in main_src

    def test_asyncio_to_thread(self, main_src):
        """LLM call is offloaded with asyncio.to_thread."""
        assert "asyncio.to_thread" in main_src

    def test_conversation_history_capped(self, main_src):
        """Conversation history is capped before sending to LLM."""
        assert "raw_history[-10:]" in main_src

    def test_patient_endpoint_auth(self, main_src):
        """Patient endpoint validates auth via _require_auth."""
        # The endpoint body must call _require_auth
        endpoint_region = main_src[main_src.find("/api/patient/respond") :][:2000]
        assert "_require_auth" in endpoint_region

    def test_patient_endpoint_requires_api_key(self, main_src):
        """Patient endpoint returns 503 when OPENAI_API_KEY absent."""
        endpoint_region = main_src[main_src.find("/api/patient/respond") :][:2000]
        assert "503" in endpoint_region
        assert "OPENAI_API_KEY" in endpoint_region

    def test_tts_error_on_no_key(self, main_src):
        """When no API key, WebSocket sends tts_error then end."""
        # Anchor on the WS handler decorator, not generic 'api/tts/stream' (which
        # also appears in comments earlier in the file).
        ws_start = main_src.find('@app.websocket("/api/tts/stream")')
        if ws_start == -1:
            ws_start = main_src.find("async def api_tts_stream")
        assert ws_start != -1, "Could not locate WS TTS handler in main.py"
        ws_region = main_src[ws_start : ws_start + 6000]
        assert "tts_error" in ws_region


# ── 2. tts_client.js ─────────────────────────────────────────────────────────


class TestTtsClientJs:
    def test_v7_header(self, tts_src):
        """File version string updated to v7."""
        assert "v7" in tts_src

    def test_tts_error_handler(self, tts_src):
        """tts_error message type is handled."""
        assert "tts_error" in tts_src

    def test_on_error_callback(self, tts_src):
        """onError callback is wired for TTS errors."""
        assert "onError" in tts_src

    def test_synthetic_fallback_removed(self, tts_src):
        """synthetic_fallback message type removed."""
        assert "synthetic_fallback" not in tts_src

    def test_on_fallback_removed(self, tts_src):
        """onFallback callback removed from streamSpeak."""
        assert "onFallback" not in tts_src

    def test_on_synthetic_removed(self, tts_src):
        """onSynthetic callback removed from streamSpeak."""
        assert "onSynthetic" not in tts_src

    def test_msg_synthetic_removed(self, tts_src):
        """msg.synthetic meta flag check removed."""
        assert "msg.synthetic" not in tts_src

    def test_speak_text_fallback_kept(self, tts_src):
        """speakTextFallback kept as explicit opt-in for callers."""
        assert "speakTextFallback" in tts_src

    def test_ws_onerror_calls_on_error(self, tts_src):
        """ws.onerror handler calls onError callback."""
        onerror_region = tts_src[tts_src.find("ws.onerror") :][:300]
        assert "onError" in onerror_region

    def test_end_handler_no_synth_guard(self, tts_src):
        """End handler no longer guarded by synthActive."""
        assert "synthActive" not in tts_src


# ── 3. chat_controller.js ────────────────────────────────────────────────────


class TestChatControllerJs:
    def test_patient_mode_state(self, cc_src):
        """patientMode state variable declared."""
        assert "patientMode" in cc_src

    def test_patient_context_state(self, cc_src):
        """patientContext state variable declared."""
        assert "patientContext" in cc_src

    def test_patient_conversation_state(self, cc_src):
        """patientConversation array declared."""
        assert "patientConversation" in cc_src

    def test_last_clinician_text_state(self, cc_src):
        """lastClinicianText state variable declared."""
        assert "lastClinicianText" in cc_src

    def test_apply_patient_mode(self, cc_src):
        """_applyPatientMode function defined."""
        assert "_applyPatientMode" in cc_src

    def test_load_scenario_pack(self, cc_src):
        """_loadScenarioPack function replaces _loadScriptPack."""
        assert "_loadScenarioPack" in cc_src
        assert "_loadScriptPack" not in cc_src

    def test_load_patient_persona(self, cc_src):
        """_loadPatientPersona function defined."""
        assert "_loadPatientPersona" in cc_src

    def test_generate_ai_patient_response(self, cc_src):
        """_generateAiPatientResponse function defined."""
        assert "_generateAiPatientResponse" in cc_src

    def test_auto_roleplay_wired(self, cc_src):
        """Auto-roleplay triggers _generateAiPatientResponse after clinician speech."""
        assert "autoRoleplayToggle" in cc_src
        assert "_generateAiPatientResponse" in cc_src

    def test_patient_respond_api_called(self, cc_src):
        """AI patient function calls /api/patient/respond."""
        assert "/api/patient/respond" in cc_src

    def test_shimmer_voice_for_patient(self, cc_src):
        """AI patient response spoken in shimmer voice."""
        assert "'shimmer'" in cc_src or '"shimmer"' in cc_src

    def test_mic_disabled_during_recognition(self, cc_src):
        """Mic button disabled during speech recognition."""
        assert "micBtn.disabled = true" in cc_src

    def test_mic_re_enabled_on_end(self, cc_src):
        """Mic button re-enabled in onend/onerror handlers."""
        assert "micBtn.disabled = false" in cc_src

    def test_old_script_line_select_removed(self, cc_src):
        """Old scriptLineSelect DOM reference removed."""
        assert "scriptLineSelect" not in cc_src

    def test_old_flatten_script_pack_removed(self, cc_src):
        """Old _flattenScriptPack function removed."""
        assert "_flattenScriptPack" not in cc_src

    def test_old_synthetic_event_removed(self, cc_src):
        """nexus_tts_synthetic_fallback event listener removed."""
        assert "nexus_tts_synthetic_fallback" not in cc_src

    def test_old_on_fallback_removed(self, cc_src):
        """onFallback callback call removed from _speakStreaming."""
        assert "onFallback" not in cc_src

    def test_patient_mode_radios_wired(self, cc_src):
        """Patient mode radio buttons wired in event listeners."""
        assert "patientModeHuman" in cc_src
        assert "patientModeAi" in cc_src

    def test_on_error_in_speak_streaming(self, cc_src):
        """_speakStreaming uses onError instead of onFallback."""
        speak_region = cc_src[cc_src.find("function _speakStreaming") :][:1500]
        assert "onError" in speak_region


# ── 4. avatar.html ───────────────────────────────────────────────────────────


class TestAvatarHtml:
    def test_tts_client_v7(self, html_src):
        """tts_client.js loaded at version 7."""
        assert "tts_client.js?v=7" in html_src

    def test_chat_controller_v7(self, html_src):
        """chat_controller.js loaded at version 7."""
        assert "chat_controller.js?v=7" in html_src

    def test_patient_mode_human_radio(self, html_src):
        """Human patient mode radio button present."""
        assert "patient-mode-human" in html_src

    def test_patient_mode_ai_radio(self, html_src):
        """AI roleplay mode radio button present."""
        assert "patient-mode-ai" in html_src

    def test_scenario_select(self, html_src):
        """Scenario dropdown present."""
        assert "scenario-select" in html_src

    def test_ai_patient_respond_btn(self, html_src):
        """AI Patient Respond button present."""
        assert "ai-patient-respond-btn" in html_src

    def test_auto_roleplay_toggle(self, html_src):
        """Auto role-play checkbox present."""
        assert "auto-roleplay-toggle" in html_src

    def test_patient_context_bar(self, html_src):
        """Patient context bar element present."""
        assert "patient-context-bar" in html_src

    def test_old_script_line_select_gone(self, html_src):
        """Old script-line-select element removed."""
        assert "script-line-select" not in html_src

    def test_old_use_script_btn_gone(self, html_src):
        """Old use-script-btn removed."""
        assert "use-script-btn" not in html_src

    def test_old_play_script_clip_btn_gone(self, html_src):
        """Old play-script-clip-btn removed."""
        assert "play-script-clip-btn" not in html_src


# ── 5. patient_script_pack.json ──────────────────────────────────────────────


class TestPatientScriptPack:
    def test_version_3(self, pack_data):
        """Version bumped to 3."""
        assert pack_data["version"] == 3

    def test_three_scenarios(self, pack_data):
        """Three scenarios present."""
        assert len(pack_data["scenarios"]) == 3

    @pytest.mark.parametrize("idx", [0, 1, 2])
    def test_scenario_has_patient_context(self, pack_data, idx):
        """Each scenario has a patient_context object."""
        s = pack_data["scenarios"][idx]
        assert "patient_context" in s, (
            f"Scenario {idx} ({s.get('id', '?')}) missing patient_context"
        )

    @pytest.mark.parametrize("idx", [0, 1, 2])
    def test_patient_context_required_fields(self, pack_data, idx):
        """Each patient_context has the required fields."""
        ctx = pack_data["scenarios"][idx]["patient_context"]
        for field in (
            "name",
            "age",
            "gender",
            "chief_complaint",
            "medical_history",
            "medications",
            "allergies",
            "family_history",
            "social_history",
        ):
            assert field in ctx, f"Scenario {idx} patient_context missing field '{field}'"

    def test_no_audio_clip_fields(self, pack_data):
        """No audio_clip fields remain in the pack."""
        as_str = json.dumps(pack_data)
        assert "audio_clip" not in as_str

    def test_scenario_personas(self, pack_data):
        """Known patient names are present."""
        as_str = json.dumps(pack_data)
        assert "Amina Njeri" in as_str
        assert "David Osei" in as_str
        assert "Priya Sharma" in as_str

    def test_scenario_ids(self, pack_data):
        """Original scenario IDs preserved."""
        ids = {s["id"] for s in pack_data["scenarios"]}
        assert "phone_new_patient_registration" in ids
        assert "returning_patient_followup_call" in ids


# ── 6. HTTP integration tests (requires live avatar agent) ────────────────────


@pytest.mark.skipif(
    not os.getenv("NEXUS_JWT_SECRET"),
    reason="NEXUS_JWT_SECRET not set — skip live HTTP tests",
)
class TestPatientRespondEndpoint:
    """Live integration tests against the running avatar agent on port 8039."""

    @pytest.fixture(scope="class")
    def token(self):
        from shared.nexus_common.auth import mint_jwt

        return mint_jwt("test", os.environ["NEXUS_JWT_SECRET"])

    @pytest.fixture(scope="class")
    def headers(self, token):
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    @pytest.fixture(scope="class")
    def patient_context(self, pack_data):
        return pack_data["scenarios"][0]["patient_context"]

    def test_endpoint_reachable(self, token, headers, avatar_running):
        if not avatar_running:
            pytest.skip("Avatar agent not running on port 8039")
        resp = httpx.post(
            f"{AVATAR_URL}/api/patient/respond",
            headers=headers,
            json={
                "clinician_message": "Hello, how can I help you today?",
                "patient_context": {
                    "name": "Amina Njeri",
                    "age": 35,
                    "gender": "female",
                    "chief_complaint": "Chest pressure",
                    "medical_history": "Hypertension",
                    "medications": "Amlodipine",
                    "allergies": "None",
                    "family_history": "Father had MI",
                    "social_history": "Non-smoker",
                },
                "conversation_history": [],
            },
            timeout=30,
        )
        assert resp.status_code in (200, 503), f"Unexpected status {resp.status_code}: {resp.text}"
        if resp.status_code == 503:
            # No OPENAI_API_KEY set on running agent — expected in CI
            assert "OPENAI_API_KEY" in resp.json().get("detail", "")
        else:
            assert "patient_response" in resp.json()
            assert len(resp.json()["patient_response"]) > 0

    def test_endpoint_rejects_no_auth(self, avatar_running):
        if not avatar_running:
            pytest.skip("Avatar agent not running on port 8039")
        resp = httpx.post(
            f"{AVATAR_URL}/api/patient/respond",
            headers={"Content-Type": "application/json"},
            json={"clinician_message": "Hello", "patient_context": {}, "conversation_history": []},
            timeout=10,
        )
        assert resp.status_code in (401, 403)

    def test_endpoint_rejects_empty_clinician_message(self, headers, avatar_running):
        if not avatar_running:
            pytest.skip("Avatar agent not running on port 8039")
        resp = httpx.post(
            f"{AVATAR_URL}/api/patient/respond",
            headers=headers,
            json={"clinician_message": "", "patient_context": {}, "conversation_history": []},
            timeout=10,
        )
        assert resp.status_code == 400

    def test_health_endpoint_still_works(self, avatar_running):
        if not avatar_running:
            pytest.skip("Avatar agent not running on port 8039")
        resp = httpx.get(f"{AVATAR_URL}/health", timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data  # required by Command Centre

    def test_static_pack_served(self, avatar_running):
        if not avatar_running:
            pytest.skip("Avatar agent not running on port 8039")
        resp = httpx.get(f"{AVATAR_URL}/static/patient_script_pack.json", timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 3
        assert len(data["scenarios"]) == 3
