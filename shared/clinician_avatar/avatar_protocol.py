"""Protocol helpers for clinician avatar JSON-RPC payloads."""

from __future__ import annotations

from typing import Any


def normalize_start_session_params(params: dict[str, Any]) -> dict[str, Any]:
    patient_case = (
        params.get("patient_case") if isinstance(params.get("patient_case"), dict) else {}
    )
    persona = params.get("persona") if isinstance(params.get("persona"), dict) else {}
    return {"patient_case": patient_case, "persona": persona}


def normalize_patient_message_params(params: dict[str, Any]) -> dict[str, Any]:
    session_id = str(params.get("session_id") or "").strip()
    message = str(params.get("message") or "").strip()
    return {"session_id": session_id, "message": message}
