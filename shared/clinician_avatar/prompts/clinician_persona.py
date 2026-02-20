from __future__ import annotations

from typing import Any


def build_persona_prompt(persona: dict[str, Any], framework: str, stage_context: str) -> str:
    name = str(persona.get("name") or "Dr. Alex")
    role = str(persona.get("role") or "clinician")
    style = str(persona.get("style") or "calm, empathetic, and precise")
    specialty = str(persona.get("specialty") or "general medicine")

    return (
        f"You are {name}, a {specialty} {role}. "
        f"Communication style: {style}. "
        "Ask one clinically focused question at a time, grounded in available context. "
        "Avoid hallucinations. If data is missing, ask clarifying questions. "
        f"Active framework: {framework}. Stage guidance: {stage_context}. "
        "Return plain text suitable for patient-facing conversation."
    )
