"""NHS/NICE-aligned clinical handoff guardrails.

This module provides deterministic, executable checks for transfer-of-care
steps in simulated patient journeys. The rules are safety-first and designed
to complement handoff prerequisite validation in tools.delegation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

# Public guideline references used in trace metadata for auditability.
GUIDELINE_REFS: dict[str, str] = {
    "structured_handover": "NICE-QS174-Statement4",
    "discharge_planning": "NICE-NG27",
    "medicines_transfer": "NICE-NG5",
    "deterioration_escalation": "NICE-QS213-Statement5",
    "sepsis_risk": "NICE-NG253",
    "accessible_information": "NHS-Accessible-Information-Standard",
    "medication_safety": "WHO-Medication-Without-Harm",
}


TRANSFER_AGENTS = {"bed_manager", "discharge", "followup", "coordinator"}

# Baseline SBAR+continuity payload requirements for transfer steps.
DEFAULT_TRANSFER_FIELDS = [
    "situation",
    "background",
    "assessment",
    "recommendation",
    "plan",
    "outstanding_tasks",
    "communication_needs",
]


@dataclass
class GuardrailResult:
    allowed: bool = True
    reason_code: str = "allowed"
    reason: str = ""
    guideline_refs: list[str] = field(default_factory=list)
    escalation_trigger: str | None = None
    senior_review_deadline: str | None = None
    handover_contract_status: str = "complete"
    safe_fallback_taken: bool = False
    missing_fields: list[str] = field(default_factory=list)

    def merge_refs(self, refs: list[str]) -> None:
        seen = set(self.guideline_refs)
        for ref in refs:
            if ref and ref not in seen:
                seen.add(ref)
                self.guideline_refs.append(ref)


def _iso_after_minutes(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=max(0, minutes))).isoformat()


def _resolve_path(payload: dict[str, Any], path: str) -> Any:
    cursor: Any = payload
    for segment in path.split("."):
        if isinstance(cursor, dict) and segment in cursor:
            cursor = cursor[segment]
        else:
            return None
    return cursor


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _handover_payload(step: dict[str, Any], clinical_context: dict[str, Any]) -> dict[str, Any]:
    params = step.get("params") if isinstance(step.get("params"), dict) else {}
    transition = params.get("care_transition") if isinstance(params.get("care_transition"), dict) else {}
    handover = transition.get("handover") if isinstance(transition.get("handover"), dict) else {}
    if handover:
        return handover
    global_handover = clinical_context.get("handover")
    if isinstance(global_handover, dict):
        return global_handover
    return {}


def _requires_transfer_contract(step: dict[str, Any]) -> bool:
    agent = str(step.get("agent", "")).strip().lower()
    method = str(step.get("method", "")).strip().lower()
    if agent in TRANSFER_AGENTS:
        return True
    transfer_tokens = ("handoff", "transfer", "admission", "discharge", "followup")
    return any(token in method for token in transfer_tokens)


def evaluate_structured_handover(
    step: dict[str, Any],
    handoff_policy: dict[str, Any] | None,
    clinical_context: dict[str, Any],
) -> GuardrailResult:
    result = GuardrailResult()
    policy = handoff_policy or {}
    required_fields = list(policy.get("required_handover_fields") or [])

    if _requires_transfer_contract(step):
        for field in DEFAULT_TRANSFER_FIELDS:
            if field not in required_fields:
                required_fields.append(field)

    if not required_fields:
        return result

    payload = _handover_payload(step, clinical_context)
    missing: list[str] = []
    for field in required_fields:
        if field.startswith("handover."):
            value = _resolve_path(payload, field.split(".", 1)[1])
        else:
            value = payload.get(field)
        if not _is_present(value):
            missing.append(field)

    if missing:
        result.allowed = False
        result.reason_code = "missing_handover_contract"
        result.reason = f"Missing structured handover fields: {', '.join(missing)}"
        result.handover_contract_status = "incomplete"
        result.missing_fields = missing
        result.escalation_trigger = "structured_handover_gap"
        result.senior_review_deadline = _iso_after_minutes(15)
    result.merge_refs(
        [
            GUIDELINE_REFS["structured_handover"],
            GUIDELINE_REFS["accessible_information"],
            GUIDELINE_REFS["medication_safety"],
        ]
    )
    return result


def evaluate_discharge_guardrails(
    step: dict[str, Any],
    clinical_context: dict[str, Any],
) -> GuardrailResult:
    result = GuardrailResult()
    agent = str(step.get("agent", "")).strip().lower()
    method = str(step.get("method", "")).strip().lower()
    if agent != "discharge" and "discharge" not in method:
        return result

    params = step.get("params") if isinstance(step.get("params"), dict) else {}
    task = params.get("task") if isinstance(params.get("task"), dict) else {}
    transition = params.get("care_transition") if isinstance(params.get("care_transition"), dict) else {}

    checks = {
        "discharge_summary": task.get("discharge_summary") or task.get("discharge_diagnosis"),
        "medication_reconciliation": task.get("medication_reconciliation_complete")
        or task.get("medications_at_discharge")
        or task.get("medications_on_discharge"),
        "followup_responsibility": transition.get("followup_responsibility")
        or params.get("followup_owner"),
        "receiving_provider_notified": transition.get("receiving_provider_notified"),
    }

    missing = [key for key, value in checks.items() if not _is_present(value)]
    if missing:
        result.allowed = False
        result.reason_code = "unsafe_discharge_prevented"
        result.reason = f"Unsafe discharge blocked; missing: {', '.join(missing)}"
        result.handover_contract_status = "incomplete"
        result.missing_fields = missing
        result.escalation_trigger = "discharge_guardrail_breach"
        result.senior_review_deadline = _iso_after_minutes(30)

    result.merge_refs(
        [
            GUIDELINE_REFS["discharge_planning"],
            GUIDELINE_REFS["medicines_transfer"],
            GUIDELINE_REFS["medication_safety"],
        ]
    )
    return result


def evaluate_deterioration_escalation(
    step: dict[str, Any],
    clinical_context: dict[str, Any],
) -> GuardrailResult:
    result = GuardrailResult()
    profile = clinical_context.get("patient_profile") if isinstance(clinical_context, dict) else {}
    params = step.get("params") if isinstance(step.get("params"), dict) else {}
    vitals = {}
    for candidate in (
        params.get("vital_signs"),
        profile.get("vital_signs") if isinstance(profile, dict) else None,
        clinical_context.get("medical_history", {}).get("vital_signs")
        if isinstance(clinical_context.get("medical_history"), dict)
        else None,
    ):
        if isinstance(candidate, dict):
            vitals = candidate
            break

    if not vitals:
        return result

    rr = float(vitals.get("respiratory_rate", 0) or 0)
    spo2 = float(vitals.get("oxygen_saturation", 0) or 0)
    sbp_raw = str(vitals.get("blood_pressure", "")).strip()
    sbp = 0.0
    if "/" in sbp_raw:
        try:
            sbp = float(sbp_raw.split("/", 1)[0].strip())
        except Exception:
            sbp = 0.0
    hr = float(vitals.get("heart_rate", 0) or 0)
    temp = float(vitals.get("temperature_c", 0) or 0)

    triggers: list[str] = []
    if rr >= 25:
        triggers.append("tachypnoea")
    if spo2 and spo2 < 92:
        triggers.append("hypoxia")
    if sbp and sbp < 90:
        triggers.append("hypotension")
    if hr >= 130:
        triggers.append("marked_tachycardia")
    if temp >= 39 or (temp and temp <= 35):
        triggers.append("temperature_extreme")

    if not triggers:
        return result

    result.escalation_trigger = ",".join(triggers)
    result.senior_review_deadline = _iso_after_minutes(60)
    result.merge_refs(
        [GUIDELINE_REFS["deterioration_escalation"], GUIDELINE_REFS["sepsis_risk"]]
    )

    # Discharge with clear deterioration signal is not safe.
    agent = str(step.get("agent", "")).strip().lower()
    method = str(step.get("method", "")).strip().lower()
    if agent == "discharge" or "discharge" in method:
        result.allowed = False
        result.reason_code = "senior_review_required"
        result.reason = "Senior clinical review required before discharge due to deterioration risk"
        result.handover_contract_status = "blocked_for_review"

    return result


def apply_nhs_guardrails(
    step: dict[str, Any],
    handoff_policy: dict[str, Any] | None,
    clinical_context: dict[str, Any],
) -> GuardrailResult:
    """Apply the NHS/NICE+WHO guardrail stack for a step."""
    checks = [
        evaluate_structured_handover(step, handoff_policy, clinical_context),
        evaluate_discharge_guardrails(step, clinical_context),
        evaluate_deterioration_escalation(step, clinical_context),
    ]

    aggregate = GuardrailResult()
    for check in checks:
        aggregate.merge_refs(check.guideline_refs)
        if check.escalation_trigger and not aggregate.escalation_trigger:
            aggregate.escalation_trigger = check.escalation_trigger
        if check.senior_review_deadline and not aggregate.senior_review_deadline:
            aggregate.senior_review_deadline = check.senior_review_deadline
        if check.handover_contract_status != "complete":
            aggregate.handover_contract_status = check.handover_contract_status
        if check.missing_fields:
            aggregate.missing_fields.extend(check.missing_fields)
        if not check.allowed:
            aggregate.allowed = False
            aggregate.reason_code = check.reason_code
            aggregate.reason = check.reason
            return aggregate

    aggregate.reason_code = "allowed"
    return aggregate
