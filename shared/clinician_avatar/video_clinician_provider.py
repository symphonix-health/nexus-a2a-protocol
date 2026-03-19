from __future__ import annotations

import asyncio
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


import re

# ── Grapheme-to-phoneme rules (English approximation) ──────────────────
# Maps letter patterns to phoneme sequences.  Each phoneme maps to one of
# 15 MPEG-4 compatible viseme classes.  Order matters: longer patterns first.

_G2P_RULES: list[tuple[str, list[str]]] = [
    # Digraphs and common clusters — must come before single letters
    ("th", ["TH"]),
    ("sh", ["CH"]),
    ("ch", ["CH"]),
    ("ph", ["FF"]),
    ("wh", ["RR"]),
    ("ck", ["KK"]),
    ("ng", ["NN"]),
    ("qu", ["KK", "RR"]),
    ("oo", ["OO"]),
    ("ou", ["OU"]),
    ("ow", ["OU"]),
    ("oi", ["OU", "EE"]),
    ("oy", ["OU", "EE"]),
    ("ea", ["EE"]),
    ("ee", ["EE"]),
    ("ai", ["EE"]),
    ("ay", ["EE"]),
    ("aw", ["OU"]),
    ("au", ["OU"]),
    ("igh", ["AA", "EE"]),
    ("tion", ["CH", "IH", "NN"]),
    ("sion", ["CH", "IH", "NN"]),
    ("ture", ["CH", "IH"]),
    ("er", ["IH", "RR"]),
    ("ir", ["IH", "RR"]),
    ("ur", ["IH", "RR"]),
    ("or", ["OU", "RR"]),
    ("ar", ["AA", "RR"]),
    ("re", ["RR", "IH"]),
    ("le", ["DD", "IH"]),
    ("ed", ["DD"]),
    ("ing", ["IH", "NN"]),
    # Single consonants
    ("b", ["PP"]),
    ("c", ["KK"]),
    ("d", ["DD"]),
    ("f", ["FF"]),
    ("g", ["KK"]),
    ("h", ["AA"]),    # aspirate — slight open mouth
    ("j", ["CH"]),
    ("k", ["KK"]),
    ("l", ["DD"]),
    ("m", ["PP"]),
    ("n", ["NN"]),
    ("p", ["PP"]),
    ("r", ["RR"]),
    ("s", ["SS"]),
    ("t", ["DD"]),
    ("v", ["FF"]),
    ("w", ["RR"]),
    ("x", ["KK", "SS"]),
    ("y", ["EE"]),
    ("z", ["SS"]),
    # Vowels
    ("a", ["AA"]),
    ("e", ["IH"]),
    ("i", ["EE"]),
    ("o", ["OU"]),
    ("u", ["OO"]),
]

# Compile rules into a sorted list (longest pattern first for greedy matching)
_G2P_RULES.sort(key=lambda r: -len(r[0]))

# Average phoneme durations (ms) — varies by viseme class
_PHONEME_DURATION: dict[str, float] = {
    "sil": 60.0,
    "PP":  80.0,
    "FF":  90.0,
    "TH":  85.0,
    "DD":  65.0,
    "KK":  70.0,
    "CH":  85.0,
    "SS":  95.0,
    "NN":  70.0,
    "RR":  75.0,
    "AA":  100.0,
    "EE":  90.0,
    "IH":  80.0,
    "OO":  95.0,
    "OU":  100.0,
}

# Emphasis weight by viseme class (stressed syllables get higher weight)
_VISEME_BASE_WEIGHT: dict[str, float] = {
    "sil": 0.0,
    "PP":  0.5,
    "FF":  0.55,
    "TH":  0.55,
    "DD":  0.6,
    "KK":  0.6,
    "CH":  0.6,
    "SS":  0.5,
    "NN":  0.5,
    "RR":  0.6,
    "AA":  0.95,
    "EE":  0.7,
    "IH":  0.65,
    "OO":  0.75,
    "OU":  0.85,
}

_WORD_STRIP_RE = re.compile(r"[^a-z]")


def _word_to_phonemes(word: str) -> list[str]:
    """Convert a single word to a sequence of viseme classes using G2P rules."""
    lower = _WORD_STRIP_RE.sub("", word.lower())
    if not lower:
        return []

    phonemes: list[str] = []
    i = 0
    while i < len(lower):
        matched = False
        for pattern, phons in _G2P_RULES:
            plen = len(pattern)
            if lower[i : i + plen] == pattern:
                phonemes.extend(phons)
                i += plen
                matched = True
                break
        if not matched:
            i += 1  # skip unknown characters

    return phonemes


def simple_viseme_timeline(text: str) -> list[dict[str, float | str]]:
    """Generate a phoneme-level viseme timeline from text.

    v2: Full grapheme-to-phoneme decomposition with 15 MPEG-4 viseme classes,
    per-phoneme timing, inter-word silence gaps, and natural weight variation.
    """
    words = [w for w in text.split() if w.strip()]
    if not words:
        return [{"time_ms": 0.0, "viseme": "sil", "weight": 0.0}]

    timeline: list[dict[str, float | str]] = []
    t = 80.0  # Start with brief silence

    for word_idx, word in enumerate(words):
        phonemes = _word_to_phonemes(word)
        if not phonemes:
            t += 60.0  # skip unknown words with a short pause
            continue

        # First syllable of content words gets slight emphasis
        is_content_word = len(word) > 3
        for p_idx, viseme in enumerate(phonemes):
            weight = _VISEME_BASE_WEIGHT.get(viseme, 0.65)
            # Emphasis: first vowel-like phoneme in longer words
            if is_content_word and p_idx < 3 and viseme in ("AA", "EE", "IH", "OO", "OU"):
                weight = min(1.0, weight * 1.15)

            timeline.append({
                "time_ms": round(t, 1),
                "viseme": viseme,
                "weight": round(weight, 2),
            })
            t += _PHONEME_DURATION.get(viseme, 75.0)

        # Inter-word gap (natural pause between words)
        if word_idx < len(words) - 1:
            # Longer pause after punctuation
            if word.rstrip()[-1:] in ".,;:!?":
                t += 140.0
            else:
                t += 55.0

    # Trailing silence
    timeline.append({"time_ms": round(t + 100.0, 1), "viseme": "sil", "weight": 0.0})
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


async def stream_tts_chunks(
    text: str,
    voice: str = "nova",
    instructions: str | None = None,
):
    """Async generator yielding raw PCM chunks (24 kHz, 16-bit, mono, little-endian).

    Yields nothing when OPENAI_API_KEY is absent or the API call fails.
    The caller (WebSocket handler) detects zero chunks and sends a
    ``tts_error`` message so the UI surfaces a visible error.

    ``instructions`` (optional) is passed to gpt-4o-mini-tts to control
    speaking style.  Falls back to a sensible clinician default when omitted.

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
    chosen_voice = voice or os.getenv("OPENAI_TTS_VOICE", "nova")
    timeout_seconds = float(os.getenv("OPENAI_TTS_TIMEOUT_SECONDS", "60"))
    max_attempts = int(os.getenv("OPENAI_TTS_MAX_ATTEMPTS", "2"))

    # Default style instructions for natural clinician speech
    _default_instructions = (
        "Speak naturally and warmly like an experienced clinician in a "
        "face-to-face consultation with a patient. Use a calm, reassuring, "
        "and empathetic conversational tone. Vary your pace naturally: "
        "slow down slightly when explaining important medical information, "
        "and use normal pace for questions. Include natural breathing pauses "
        "between sentences. Add subtle vocal warmth and slight emphasis on "
        "key medical terms. Occasionally use brief filler-like pauses "
        "(short hesitations) as a real doctor would when thinking. "
        "Never sound robotic, monotone, or like you are reading from a script. "
        "Speak as if the patient is sitting right in front of you."
    )
    tts_instructions = instructions or os.getenv(
        "OPENAI_TTS_INSTRUCTIONS", _default_instructions
    )

    url = "https://api.openai.com/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model,
        "voice": chosen_voice,
        "input": clean,
        "response_format": "pcm",  # raw 24 kHz 16-bit mono PCM
    }
    # gpt-4o-mini-tts supports the `instructions` field for style control
    if tts_instructions:
        payload["instructions"] = tts_instructions
    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        continue
                    async for chunk in response.aiter_bytes(chunk_size=4800):
                        yield chunk
                    return
        except Exception:  # noqa: BLE001
            pass
        if attempt < max_attempts:
            await asyncio.sleep(0.35)
    # API failure — WebSocket handler detects zero chunks and sends fallback.
    return


def get_video_clinician_provider() -> VideoClinicianProvider:
    key = str(os.getenv("VIDEO_CLINICIAN_PROVIDER", "local_gpu")).strip().lower()
    if key in {"did", "d-id", "d_id"}:
        return DidVideoClinicianProvider()
    if key in {"sync", "syncso", "synclabs"}:
        return SyncVideoClinicianProvider()
    return LocalGpuVideoClinicianProvider()
