from __future__ import annotations

from shared.clinician_avatar.video_clinician_provider import (
    DidVideoClinicianProvider,
    LocalGpuVideoClinicianProvider,
    SyncVideoClinicianProvider,
    get_video_clinician_provider,
)


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


def test_remote_provider_falls_back_without_endpoint(monkeypatch):
    monkeypatch.delenv("DID_VIDEO_CLINICIAN_ENDPOINT", raising=False)
    monkeypatch.delenv("DID_API_KEY", raising=False)
    provider = DidVideoClinicianProvider()

    payload = provider.render("I have chest pain.", voice="alloy", context={"session_id": "s1"})

    assert payload["provider"] == "did"
    assert payload["provider_status"] == "fallback"
    assert payload["speech"]["mime_type"] == "audio/wav"
    assert isinstance(payload["speech"]["audio_b64"], str)
