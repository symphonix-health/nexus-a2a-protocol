from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PACK_PATH = (
    REPO_ROOT
    / "demos"
    / "helixcare"
    / "clinician-avatar-agent"
    / "app"
    / "static"
    / "patient_script_pack.json"
)
AVATAR_DIR = REPO_ROOT / "avatar"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _flatten_lines(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    for item in payload.get("lines", []) or []:
        if isinstance(item, str):
            out.append({"id": _slug(item[:40]), "text": item})
        elif isinstance(item, dict):
            text = str(item.get("text") or "").strip()
            if text:
                out.append(item)

    for scenario in payload.get("scenarios", []) or []:
        scenario_id = str(scenario.get("id") or "scenario")
        for item in scenario.get("lines", []) or []:
            if isinstance(item, str):
                out.append(
                    {
                        "id": f"{scenario_id}_{_slug(item[:40])}",
                        "text": item,
                    }
                )
            elif isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                if text:
                    out.append(item)

    return out


def _resolve_filename(line: dict[str, Any]) -> str:
    explicit = str(line.get("audio_clip") or "").strip()
    if explicit:
        return explicit
    line_id = str(line.get("id") or "line")
    return f"{_slug(line_id)}.wav"


def main() -> int:
    if not SCRIPT_PACK_PATH.exists():
        print(f"Script pack not found: {SCRIPT_PACK_PATH}")
        return 1

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("OPENAI_API_KEY is required.")
        return 1

    voice = os.getenv("PATIENT_SCRIPT_TTS_VOICE", "nova")
    model = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")

    payload = json.loads(SCRIPT_PACK_PATH.read_text(encoding="utf-8"))
    lines = _flatten_lines(payload)

    if not lines:
        print("No lines found in patient_script_pack.json")
        return 1

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    client = OpenAI(api_key=api_key)

    written = 0
    for line in lines:
        text = str(line.get("text") or "").strip()
        if not text:
            continue

        filename = _resolve_filename(line)
        target = AVATAR_DIR / filename

        try:
            with client.audio.speech.with_streaming_response.create(
                model=model,
                voice=voice,
                input=text,
                format="wav",
            ) as response:
                response.stream_to_file(target)
            written += 1
            print(f"wrote: {target.name}")
        except Exception as exc:  # noqa: BLE001
            print(f"failed: {filename} -> {exc}")

    print(f"done: wrote {written} clip(s) to {AVATAR_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
