from __future__ import annotations

import pytest

from shared.clinician_avatar.video_clinician_provider import (
    DidVideoClinicianProvider,
    LocalGpuVideoClinicianProvider,
    SyncVideoClinicianProvider,
    get_video_clinician_provider,
    has_openai_tts,
    simple_viseme_timeline,
    stream_tts_chunks,
)


# ── Provider factory ──────────────────────────────────────────────────────────


def test_provider_factory_defaults_to_local(monkeypatch):
    monkeypatch.delenv("VIDEO_CLINICIAN_PROVIDER", raising=False)
    provider = get_video_clinician_provider()
    assert isinstance(provider, LocalGpuVideoClinicianProvider)


def test_provider_factory_selects_did(monkeypatch):
    monkeypatch.setenv("VIDEO_CLINICIAN_PROVIDER", "did")
    provider = get_video_clinician_provider()
    assert isinstance(provider, DidVideoClinicianProvider)


def test_provider_factory_selects_sync(monkeypatch):
    monkeypatch.setenv("VIDEO_CLINICIAN_PROVIDER", "sync")
    provider = get_video_clinician_provider()
    assert isinstance(provider, SyncVideoClinicianProvider)


def test_local_provider_render_shape():
    provider = LocalGpuVideoClinicianProvider()
    payload = provider.render("Hello, how are you feeling today?", voice="alloy")

    assert payload["provider"] == "local_gpu"
    assert payload["speech"]["mime_type"] == "audio/wav"
    assert payload["speech"]["voice"] == "alloy"
    assert payload["speech"]["text"].startswith("Hello")
    assert isinstance(payload["speech"]["visemes"], list)
    assert isinstance(payload["speech"]["audio_b64"], str)


def test_local_provider_no_key_returns_empty_audio(monkeypatch):
    """Without OPENAI_API_KEY the render payload must still be valid but audio_b64 is empty."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = LocalGpuVideoClinicianProvider()
    payload = provider.render("Test phrase.", voice="alloy")
    assert payload["provider"] == "local_gpu"
    assert payload["speech"]["audio_b64"] == ""
    assert isinstance(payload["speech"]["visemes"], list)


def test_remote_provider_falls_back_without_endpoint(monkeypatch):
    monkeypatch.delenv("DID_VIDEO_CLINICIAN_ENDPOINT", raising=False)
    monkeypatch.delenv("DID_API_KEY", raising=False)
    provider = DidVideoClinicianProvider()

    payload = provider.render("I have chest pain.", voice="alloy", context={"session_id": "s1"})

    assert payload["provider"] == "did"
    assert payload["provider_status"] == "fallback"
    assert payload["speech"]["mime_type"] == "audio/wav"
    assert isinstance(payload["speech"]["audio_b64"], str)


# ── has_openai_tts ────────────────────────────────────────────────────────────


def test_has_openai_tts_false_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert has_openai_tts() is False


def test_has_openai_tts_false_with_empty_string(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    assert has_openai_tts() is False


def test_has_openai_tts_true_with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-abc123")
    assert has_openai_tts() is True


# ── simple_viseme_timeline ────────────────────────────────────────────────────


def test_viseme_empty_text_returns_silence():
    result = simple_viseme_timeline("")
    assert result == [{"time_ms": 0.0, "viseme": "sil", "weight": 0.0}]


def test_viseme_whitespace_returns_silence():
    result = simple_viseme_timeline("   ")
    assert result == [{"time_ms": 0.0, "viseme": "sil", "weight": 0.0}]


def test_viseme_word_count_exceeds_word_count():
    """Phoneme-level decomposition: more entries than word count + silence."""
    result = simple_viseme_timeline("hello how are you")
    # v2: phoneme-level decomposition produces multiple entries per word
    assert len(result) > 4  # at least 1 per word + silence
    assert result[-1]["viseme"] == "sil"


def test_viseme_last_entry_is_silence():
    result = simple_viseme_timeline("test phrase here")
    last = result[-1]
    assert last["viseme"] == "sil"
    assert last["weight"] == 0.0


def test_viseme_times_increase_monotonically():
    result = simple_viseme_timeline("one two three four five")
    times = [e["time_ms"] for e in result]
    assert times == sorted(times)
    assert times[0] < times[-1]


def test_viseme_ff_for_labio_dental():
    """v2 uses FF (not FV) for labiodental fricatives (f, v)."""
    result = simple_viseme_timeline("fever")
    visemes = [e["viseme"] for e in result if e["viseme"] != "sil"]
    assert "FF" in visemes  # 'f' maps to FF in v2


def test_viseme_pp_for_bilabial():
    result = simple_viseme_timeline("back pain")
    assert result[0]["viseme"] == "PP"


def test_viseme_ou_for_round_vowels():
    """v2 uses OU (not OW) for open rounded vowels (o, ou, ow)."""
    result = simple_viseme_timeline("out")
    visemes = [e["viseme"] for e in result if e["viseme"] != "sil"]
    assert "OU" in visemes  # 'ou' maps to OU in v2


def test_viseme_ee_for_front_vowels():
    """v2 decomposes 'see' into SS + EE phonemes."""
    result = simple_viseme_timeline("see")
    visemes = [e["viseme"] for e in result if e["viseme"] != "sil"]
    assert "EE" in visemes  # 'ee' maps to EE in v2


def test_viseme_weights_in_range():
    result = simple_viseme_timeline("Hello my name is doctor Smith")
    for entry in result:
        assert 0.0 <= entry["weight"] <= 1.0


# ── stream_tts_chunks — no API key yields nothing ─────────────────────────────
# The sine-wave fallback was removed (Phase 2).  Without OPENAI_API_KEY the
# generator must yield zero chunks so the WebSocket handler sends
# {"type": "synthetic_fallback"} and the browser falls back to SpeechSynthesis.


@pytest.mark.asyncio
async def test_stream_tts_empty_yields_nothing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    chunks = [c async for c in stream_tts_chunks("")]
    assert chunks == []


@pytest.mark.asyncio
async def test_stream_tts_whitespace_yields_nothing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    chunks = [c async for c in stream_tts_chunks("   ")]
    assert chunks == []


@pytest.mark.asyncio
async def test_stream_tts_no_key_yields_nothing_for_real_text(monkeypatch):
    """Without API key, stream yields no chunks (caller sends synthetic_fallback)."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    chunks = [c async for c in stream_tts_chunks("Hello, I am Dr. Marcus.")]
    assert chunks == [], f"Expected no chunks without API key, got {len(chunks)}"


@pytest.mark.asyncio
async def test_stream_tts_no_key_yields_nothing_long_text(monkeypatch):
    """Longer text still yields nothing without API key."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    chunks = [c async for c in stream_tts_chunks(
        "Good morning. I understand you are experiencing chest pain. "
        "Can you tell me when it started and whether it radiates to your arm?"
    )]
    assert chunks == []
