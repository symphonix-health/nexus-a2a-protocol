"""Healthcare-oriented helpers for hybrid profile adapters.

The module intentionally keeps checks minimal and illustrative to avoid embedding
licensed implementation-guide semantics in the core runtime.
"""

from __future__ import annotations

from typing import Any

_REQUIRED_NCPDP_FIELDS = {
    "BIN",
    "PCN",
    "Group",
    "CardholderID",
    "RxNumber",
    "FillNumber",
    "NDC",
    "Quantity",
    "DaysSupply",
    "PrescriberID",
    "PharmacyNPI",
}


def classify_x12_transaction(edi_text: str) -> str | None:
    """Classify an X12 payload using ST segment transaction code."""
    for segment in edi_text.split("~"):
        segment = segment.strip()
        if not segment.startswith("ST*"):
            continue
        fields = segment.split("*")
        if len(fields) < 2:
            return None
        code = fields[1].strip()
        if code in {"270", "271", "278", "837", "835", "276", "277", "834"}:
            return code
    return None


def validate_minimal_x12(edi_text: str) -> tuple[bool, str]:
    required_segments = ("ISA*", "GS*", "ST*", "SE*", "GE*", "IEA*")
    for marker in required_segments:
        if marker not in edi_text:
            return False, f"Missing required segment marker: {marker}"
    tx = classify_x12_transaction(edi_text)
    if tx is None:
        return False, "Unable to classify X12 transaction from ST segment"
    return True, tx


def validate_minimal_ncpdp_claim(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    missing = [field for field in sorted(_REQUIRED_NCPDP_FIELDS) if field not in payload]
    return len(missing) == 0, missing


def validate_minimal_fhir_resource(resource: dict[str, Any]) -> tuple[bool, str]:
    resource_type = str(resource.get("resourceType") or "").strip()
    if not resource_type:
        return False, "resourceType is required"

    resource_id = str(resource.get("id") or "").strip()
    if not resource_id:
        return False, "id is required"

    if resource_type == "Patient":
        if "name" not in resource:
            return False, "Patient.name is required"
        if "birthDate" not in resource:
            return False, "Patient.birthDate is required"

    if resource_type == "Encounter":
        if "subject" not in resource:
            return False, "Encounter.subject is required"
        if "status" not in resource:
            return False, "Encounter.status is required"

    return True, resource_type


def canonical_event_template(event_type: str, correlation_id: str) -> dict[str, Any]:
    return {
        "eventType": event_type,
        "correlationId": correlation_id,
        "entities": {},
        "payload": {},
    }
