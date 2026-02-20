from __future__ import annotations

from typing import Any

STAGES = [
    "initiating",
    "gathering_information",
    "physical_examination",
    "explanation_and_planning",
    "closing",
]


def next_stage(current: str) -> str:
    if current not in STAGES:
        return STAGES[0]
    idx = STAGES.index(current)
    return STAGES[min(idx + 1, len(STAGES) - 1)]


def stage_prompt_context(stage: str) -> str:
    mapping = {
        "initiating": "Greet patient, confirm identity, open consultation agenda.",
        "gathering_information": "Use open-to-closed questions, explore ICE (ideas/concerns/expectations).",
        "physical_examination": "Explain focused exam intent and expected findings.",
        "explanation_and_planning": "Explain differential and plan with shared decision-making.",
        "closing": "Summarize, safety-net advice, and follow-up plan.",
    }
    return mapping.get(stage, mapping["gathering_information"])


def progress_update(progress: dict[str, Any], patient_message: str) -> dict[str, Any]:
    out = dict(progress)
    asked = int(out.get("turns", 0)) + 1
    out["turns"] = asked
    if asked >= 2 and out.get("stage") == "initiating":
        out["stage"] = "gathering_information"
    return out
