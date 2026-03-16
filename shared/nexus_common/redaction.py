"""PHI redaction utility for clinical trace payloads.

Provides field-level scrubbing of Protected Health Information (PHI)
before trace data is displayed or persisted.  Clinically relevant fields
(age, symptoms, medications, diagnosis candidates) are preserved so the
trace remains useful for clinical review.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

# Keys whose *values* must always be masked (case-insensitive match).
_PHI_KEYS: set[str] = {
    "name",
    "patient_name",
    "first_name",
    "last_name",
    "full_name",
    "mrn",
    "medical_record_number",
    "dob",
    "date_of_birth",
    "birth_date",
    "phone",
    "phone_number",
    "mobile",
    "email",
    "email_address",
    "address",
    "street",
    "city",
    "zip",
    "zip_code",
    "postal_code",
    "ssn",
    "social_security",
    "insurance_id",
    "insurance_number",
    "policy_number",
    "subscriber_id",
    "national_id",
    "passport",
    "drivers_license",
}

# Keys that should *never* be redacted — clinically useful context.
_SAFE_KEYS: set[str] = {
    "age",
    "gender",
    "chief_complaint",
    "urgency",
    "symptoms",
    "differential_diagnosis",
    "med_plan",
    "allergies",
    "current_medications",
    "drugs",
    "discharge_diagnosis",
    "discharge_disposition",
    "followup_instructions",
    "conditions",
    "modality",
    "visit_mode",
    "specialty",
    "complaint",
    "orders",
    "type",
    "priority",
    "indication",
    "unit_pref",
    "decision",
    "coordination_tasks",
    "journey_type",
    "reason",
    "purpose",
    "when",
    "followup_schedule",
    "monthly_minutes",
}

_JWT_PATTERN = re.compile(r"^(?:Bearer\s+)?eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")


def _is_jwt(value: str) -> bool:
    return bool(_JWT_PATTERN.match(value.strip()))


def _should_redact_key(key: str) -> bool:
    normalized = key.strip().lower()
    if normalized in _SAFE_KEYS:
        return False
    return normalized in _PHI_KEYS


def _redact_value(value: Any, key: str, masked_keys: list[str], path: str) -> Any:
    """Recursively redact a single value, recording masked field paths."""
    if isinstance(value, dict):
        return _redact_dict(value, masked_keys, path)
    if isinstance(value, list):
        return [_redact_value(item, key, masked_keys, f"{path}[]") for item in value]
    if isinstance(value, str) and _is_jwt(value):
        masked_keys.append(f"{path} (jwt)")
        return REDACTED
    return value


def _redact_dict(
    data: dict[str, Any],
    masked_keys: list[str],
    path: str = "",
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in data.items():
        field_path = f"{path}.{key}" if path else key
        if _should_redact_key(key):
            masked_keys.append(field_path)
            result[key] = REDACTED
        else:
            result[key] = _redact_value(value, key, masked_keys, field_path)
    return result


def detect_structured_phi(text: str) -> list[dict[str, str]]:
    """Detect structured PHI patterns in free text (Layer 3 -- Mitigation 2.3).

    Scans for common PHI format patterns: SSN, NHS numbers, phone numbers,
    email addresses, dates of birth, MRN formats, Irish PPS numbers.

    Returns a list of dicts with 'pattern' and 'match' keys.
    """
    _patterns: dict[str, str] = {
        "us_ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "nhs_number": r"\b\d{3}\s?\d{3}\s?\d{4}\b",
        "us_phone": r"\b\(\d{3}\)\s?\d{3}-\d{4}\b",
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "date_of_birth": r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        "mrn_format": r"\bMRN[\s:-]?\d{4,}\b",
        "ie_pps": r"\b\d{7}[A-Z]{1,2}\b",
    }
    findings: list[dict[str, str]] = []
    for name, pattern in _patterns.items():
        for match in re.finditer(pattern, text):
            findings.append({"pattern": name, "match": match.group()})
    return findings


def redact_payload(
    data: dict[str, Any] | None,
    policy: str = "v1",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Redact PHI from a JSON-serialisable dict.

    Returns:
        (redacted_data, redaction_meta) where redaction_meta records which
        fields were masked and the policy version applied.
    """
    if not data:
        return {}, {"masked_fields": [], "policy_version": policy}

    masked_keys: list[str] = []
    redacted = _redact_dict(dict(data), masked_keys, "")
    meta = {
        "masked_fields": sorted(set(masked_keys)),
        "policy_version": policy,
    }
    return redacted, meta
