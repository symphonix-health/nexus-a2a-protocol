"""Protocol helpers for clinician avatar JSON-RPC payloads."""

from __future__ import annotations

from typing import Any


def normalize_start_session_params(params: dict[str, Any]) -> dict[str, Any]:
    patient_case = (
        params.get("patient_case") if isinstance(params.get("patient_case"), dict) else {}
    )
    persona = params.get("persona") if isinstance(params.get("persona"), dict) else {}
    # Optional registry-based persona selection fields
    persona_id = str(params.get("persona_id") or "").strip()
    country = str(params.get("country") or "").strip().lower()
    care_setting = str(params.get("care_setting") or "").strip().lower()
    return {
        "patient_case": patient_case,
        "persona": persona,
        "persona_id": persona_id,
        "country": country,
        "care_setting": care_setting,
    }


def normalize_patient_message_params(params: dict[str, Any]) -> dict[str, Any]:
    session_id = str(params.get("session_id") or "").strip()
    message = str(params.get("message") or "").strip()
    return {"session_id": session_id, "message": message}
