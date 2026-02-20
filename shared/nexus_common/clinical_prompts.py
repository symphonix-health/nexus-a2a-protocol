"""Domain-specific clinical prompt templates and deterministic investigation mappings.

These helpers are intentionally light-weight at first. They provide JSON schema
instructions to the LLM and deterministic investigation ordering so the LLM only
fills in result values and narrative, not which tests to order.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# Deterministic investigation lookup by complaint + urgency
# NOTE: This is a small seed to start. Extend as scenarios are enriched.
INVESTIGATION_LOOKUP: dict[tuple[str, str], list[str]] = {
    ("chest pain", "critical"): [
        "ecg_12lead",
        "troponin_i",
        "bnp",
        "cbc",
        "bmp",
        "chest_xray",
    ],
    ("chest pain", "high"): ["ecg_12lead", "troponin_i", "cbc", "bmp", "chest_xray"],
    ("migraine", "low"): ["cbc", "bmp"],
    ("asthma", "high"): ["chest_xray", "abg_optional"],
}


def investigations_for(chief_complaint: str, urgency: str) -> list[str]:
    """Return a deterministic ordered list of investigations for complaint + urgency.

    Falls back to [] if unknown.
    """
    key = (chief_complaint.strip().lower(), urgency.strip().lower())
    return list(INVESTIGATION_LOOKUP.get(key, []))


# --- Prompt templates -------------------------------------------------------


def _json_header(schema_hint: str) -> str:
    return (
        "You MUST respond in JSON only. Do not include markdown fences. "
        f"The JSON schema is: {schema_hint}."
    )


def imaging_prompt(patient_context: dict[str, Any], study_type: str) -> tuple[str, str]:
    system = (
        "You are a careful radiologist. Provide a concise, clinically useful report. "
        + _json_header(
            '{"study_type": str, "findings": str, "impression": str, '
            '"critical": bool, "recommendations": [str]}'
        )
    )
    user = (
        "Patient context: "
        + str({k: patient_context.get(k) for k in ("patient_profile", "medical_history")})
        + f"; Study: {study_type}."
    )
    return system, user


def lab_prompt(patient_context: dict[str, Any], tests: Iterable[str]) -> tuple[str, str]:
    system = (
        "You are a clinical lab system. Generate realistic lab results with reference ranges and H/L/critical flags. "
        + _json_header(
            '{"panel": [{"test": str, "value": float | str, "unit": str, '
            '"ref_range": str, "flag": "N"|"H"|"L"|"C"}]}'
        )
    )
    user = (
        "Patient context: "
        + str({k: patient_context.get(k) for k in ("patient_profile", "medical_history")})
        + "; Ordered tests: "
        + ",".join(tests)
    )
    return system, user


def pharmacy_prompt(patient_context: dict[str, Any]) -> tuple[str, str]:
    system = (
        "You are a pharmacist. Produce a safe, guideline-concordant plan with dosing, interactions, and contraindications. "
        + _json_header(
            '{"plan": [{"drug": str, "dose": str, "route": str, "frequency": str}], '
            '"interactions": [str], "cautions": [str]}'
        )
    )
    user = "Patient context: " + str(
        {k: patient_context.get(k) for k in ("patient_profile", "medical_history", "agent_outputs")}
    )
    return system, user


def diagnosis_prompt(patient_context: dict[str, Any]) -> tuple[str, str]:
    system = (
        "You are a clinician. Provide a differential diagnosis with probabilities and a one-sentence rationale. "
        + _json_header(
            '{"differential": [{"condition": str, "prob": float}], "rationale": str, "urgency": "low|medium|high|critical"}'
        )
    )
    user = "Patient context: " + str(
        {k: patient_context.get(k) for k in ("patient_profile", "medical_history", "agent_outputs")}
    )
    return system, user
