from __future__ import annotations

import base64
import json
import math
import os
import struct
import urllib.error
import urllib.request
import wave
from abc import ABC, abstractmethod
from io import BytesIO
from typing import Any


def simple_viseme_timeline(text: str) -> list[dict[str, float | str]]:
    words = [w for w in text.split() if w.strip()]
    if not words:
        return [{"time_ms": 0.0, "viseme": "sil", "weight": 0.0}]

    timeline: list[dict[str, float | str]] = []
    t = 0.0
    for word in words:
        lower = word.lower()
        viseme = "AA"
        if any(ch in lower for ch in "fvm"):
            viseme = "FV"
        elif any(ch in lower for ch in "bp"):
            viseme = "PP"
        elif any(ch in lower for ch in "ou"):
            viseme = "OW"
        elif any(ch in lower for ch in "ei"):
            viseme = "EE"
        timeline.append({"time_ms": t, "viseme": viseme, "weight": 0.9})
        t += 190.0
    timeline.append({"time_ms": t + 120.0, "viseme": "sil", "weight": 0.0})
    return timeline


def has_openai_tts() -> bool:
    """Return True if OPENAI_API_KEY is set and real TTS synthesis is available."""
    return bool(os.getenv("OPENAI_API_KEY"))


def _generate_fallback_speech_wav_b64(text: str, duration_seconds: float = 1.4) -> str:
    sample_rate = 24000
    cleaned = str(text or "").strip()
    if cleaned:
        approx = max(1.1, min(4.5, len(cleaned) * 0.055))
        duration_seconds = max(duration_seconds, approx)

    n_samples = max(1, int(duration_seconds * sample_rate))
    buffer = BytesIO()
    wf: wave.Wave_write = wave.open(buffer, "wb")  # type: ignore[assignment]
    try:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(n_samples):
            t = i / sample_rate
            f0 = 155.0 + 35.0 * math.sin(2.0 * math.pi * 0.7 * t)
            carrier = (
                0.70 * math.sin(2.0 * math.pi * f0 * t)
                + 0.22 * math.sin(2.0 * math.pi * (2.0 * f0) * t)
                + 0.08 * math.sin(2.0 * math.pi * (3.0 * f0) * t)
            )
            envelope = 0.94 * (0.35 + 0.65 * (0.5 + 0.5 * math.sin(2.0 * math.pi * 3.8 * t)))
            sample = int(max(-32767, min(32767, carrier * envelope * 22000)))
            wf.writeframes(struct.pack("<h", sample))
    finally:
        wf.close()
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _synthesize_openai_tts_wav_b64(text: str, voice: str) -> str | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
        chosen_voice = voice or os.getenv("OPENAI_TTS_VOICE", "alloy")
        response = client.audio.speech.create(
            model=model,
            voice=chosen_voice,
            input=text,
            format="wav",
        )
        if hasattr(response, "read"):
            audio_bytes = response.read()
        elif hasattr(response, "content"):
            audio_bytes = response.content
        else:
            audio_bytes = bytes(response)
        if not audio_bytes:
            return None
        return base64.b64encode(audio_bytes).decode("ascii")
    except Exception:
        return None


class VideoClinicianProvider(ABC):
    provider_id = "base"

    @abstractmethod
    def render(
        self,
        text: str,
        voice: str = "alloy",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Render speech/video output for clinician response.

        Returns a normalized payload shape:
        {
          "provider": "...",
          "speech": {
            "voice": str,
            "mime_type": "audio/wav",
            "audio_b64": str,
            "text": str,
            "visemes": [...]
          },
          "video": { ... optional provider-specific metadata ... }
        }
        """


class LocalGpuVideoClinicianProvider(VideoClinicianProvider):
    provider_id = "local_gpu"

    def render(
        self,
        text: str,
        voice: str = "alloy",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _ = context
        clean_text = str(text or "").strip()
        if not clean_text:
            return {
                "provider": self.provider_id,
                "speech": {
                    "voice": voice,
                    "mime_type": "audio/wav",
                    "audio_b64": "",
                    "text": "",
                    "visemes": [{"time_ms": 0.0, "viseme": "sil", "weight": 0.0}],
                },
                "video": {"mode": "audio_only", "renderer": "local"},
            }

        # When OPENAI_API_KEY is absent, audio_b64 is intentionally empty.
        # The /api/tts/stream WebSocket sends synthetic_fallback so the browser
        # uses its own SpeechSynthesis — no robotic sine-wave fallback.
        audio_b64 = _synthesize_openai_tts_wav_b64(clean_text, voice) or ""

        return {
            "provider": self.provider_id,
            "speech": {
                "voice": voice,
                "mime_type": "audio/wav",
                "audio_b64": audio_b64,
                "text": clean_text,
                "visemes": simple_viseme_timeline(clean_text),
            },
            "video": {
                "mode": "audio_only",
                "renderer": os.getenv("LOCAL_GPU_VIDEO_RENDERER", "threejs-lipsync"),
            },
        }


class _RemoteJsonVideoClinicianProvider(VideoClinicianProvider):
    endpoint_env = ""
    api_key_env = ""
    timeout_env = "VIDEO_CLINICIAN_PROVIDER_TIMEOUT_SECONDS"

    def __init__(self, fallback: VideoClinicianProvider | None = None) -> None:
        self._fallback = fallback or LocalGpuVideoClinicianProvider()

    def _endpoint(self) -> str:
        return str(os.getenv(self.endpoint_env, "")).strip()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        key = str(os.getenv(self.api_key_env, "")).strip() if self.api_key_env else ""
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def _timeout_seconds(self) -> float:
        raw = os.getenv(self.timeout_env, "15")
        try:
            return max(1.0, float(raw))
        except ValueError:
            return 15.0

    @staticmethod
    def _normalize_remote_payload(data: dict[str, Any], text: str, voice: str) -> dict[str, Any]:
        speech = data.get("speech") if isinstance(data.get("speech"), dict) else {}

        speech_text = str(speech.get("text") or data.get("text") or text).strip()
        speech_voice = str(speech.get("voice") or data.get("voice") or voice).strip() or "alloy"
        mime_type = str(speech.get("mime_type") or data.get("mime_type") or "audio/wav")
        audio_b64 = str(speech.get("audio_b64") or data.get("audio_b64") or "")
        visemes = (
            speech.get("visemes")
            if isinstance(speech.get("visemes"), list)
            else data.get("visemes")
        )
        if not isinstance(visemes, list):
            visemes = simple_viseme_timeline(speech_text)

        video = data.get("video") if isinstance(data.get("video"), dict) else {}
        if not video:
            video = {
                "mode": "remote",
                "stream_url": data.get("stream_url"),
                "video_url": data.get("video_url"),
                "job_id": data.get("job_id"),
            }

        return {
            "speech": {
                "voice": speech_voice,
                "mime_type": mime_type,
                "audio_b64": audio_b64,
                "text": speech_text,
                "visemes": visemes,
            },
            "video": video,
        }

    def _call_remote(
        self,
        text: str,
        voice: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        endpoint = self._endpoint()
        if not endpoint:
            return None

        body = json.dumps({"text": text, "voice": voice, "context": context or {}}).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds()) as response:
                content = response.read()
                parsed = json.loads(content.decode("utf-8")) if content else {}
                return parsed if isinstance(parsed, dict) else {}
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
            return None

    def render(
        self,
        text: str,
        voice: str = "alloy",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        remote = self._call_remote(text, voice, context)
        if not remote:
            fallback = self._fallback.render(text, voice, context)
            fallback["provider"] = self.provider_id
            fallback["video"] = {
                "mode": "fallback",
                "fallback_provider": fallback.get("provider", "local_gpu"),
            }
            fallback["provider_status"] = "fallback"
            return fallback

        normalized = self._normalize_remote_payload(remote, text, voice)
        if not str(normalized["speech"].get("audio_b64") or ""):
            fallback = self._fallback.render(text, voice, context)
            normalized["speech"]["audio_b64"] = fallback.get("speech", {}).get("audio_b64", "")

        return {
            "provider": self.provider_id,
            "speech": normalized["speech"],
            "video": normalized["video"],
            "provider_status": "ok",
        }


class DidVideoClinicianProvider(_RemoteJsonVideoClinicianProvider):
    provider_id = "did"
    endpoint_env = "DID_VIDEO_CLINICIAN_ENDPOINT"
    api_key_env = "DID_API_KEY"


class SyncVideoClinicianProvider(_RemoteJsonVideoClinicianProvider):
    provider_id = "sync"
    endpoint_env = "SYNC_VIDEO_CLINICIAN_ENDPOINT"
    api_key_env = "SYNC_API_KEY"


async def stream_tts_chunks(text: str, voice: str = "alloy"):
    """Async generator yielding raw PCM chunks (24 kHz, 16-bit, mono, little-endian).

    Yields nothing when OPENAI_API_KEY is absent or the API call fails.
    The caller (WebSocket handler) detects zero chunks and sends a
    ``synthetic_fallback`` message so the browser uses SpeechSynthesis instead.

    Uses httpx directly because the OpenAI SDK's with_streaming_response context
    manager hangs indefinitely on Windows (ProactorEventLoop + httpx issue in SDK v2).
    """
    clean = str(text or "").strip()
    if not clean:
        return

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return  # no key — WebSocket handler will send synthetic_fallback

    import httpx

    model = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    chosen_voice = voice or os.getenv("OPENAI_TTS_VOICE", "alloy")
    url = "https://api.openai.com/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "voice": chosen_voice,
        "input": clean,
        "response_format": "pcm",  # raw 24 kHz 16-bit mono PCM
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    return
                async for chunk in response.aiter_bytes(chunk_size=4800):
                    yield chunk
    except Exception:  # noqa: BLE001
        return  # API failure — WebSocket handler detects zero chunks → synthetic_fallback


def get_video_clinician_provider() -> VideoClinicianProvider:
    key = str(os.getenv("VIDEO_CLINICIAN_PROVIDER", "local_gpu")).strip().lower()
    if key in {"did", "d-id", "d_id"}:
        return DidVideoClinicianProvider()
    if key in {"sync", "syncso", "synclabs"}:
        return SyncVideoClinicianProvider()
    return LocalGpuVideoClinicianProvider()
