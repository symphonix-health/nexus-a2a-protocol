from __future__ import annotations

ABCDE_STEPS = ["airway", "breathing", "circulation", "disability", "exposure"]


def initial_progress() -> dict[str, list[str]]:
    return {"completed": [], "remaining": list(ABCDE_STEPS)}
