from __future__ import annotations

from typing import Any

SOCRATES_KEYS = [
    "site",
    "onset",
    "character",
    "radiation",
    "associations",
    "time_course",
    "exacerbating_relieving",
    "severity",
]


def initial_progress() -> dict[str, Any]:
    return {"completed": [], "remaining": list(SOCRATES_KEYS)}


def update_progress(progress: dict[str, Any], patient_message: str) -> dict[str, Any]:
    msg = patient_message.lower()
    completed = list(progress.get("completed", []))
    remaining = [k for k in SOCRATES_KEYS if k not in completed]

    keyword_map = {
        "severity": ["/10", "pain scale", "severe", "mild"],
        "onset": ["started", "since", "sudden", "gradual"],
        "site": ["left", "right", "chest", "abdomen", "head"],
        "radiation": ["radiat", "spread", "to my arm", "to my back"],
        "character": ["sharp", "dull", "pressure", "burning", "crushing"],
        "associations": ["nausea", "sweat", "shortness of breath", "vomit"],
        "time_course": ["constant", "comes and goes", "intermittent"],
        "exacerbating_relieving": ["worse", "better", "relieved", "aggravated"],
    }
    for key in remaining:
        hints = keyword_map.get(key, [])
        if any(h in msg for h in hints):
            completed.append(key)

    completed = [k for k in SOCRATES_KEYS if k in completed]
    return {
        "completed": completed,
        "remaining": [k for k in SOCRATES_KEYS if k not in completed],
    }
