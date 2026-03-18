"""Seed GHARRA with ALL agents that should be registered.

Registers 47 agents total:
  - 4 canonical e2e agents (from GHARRA tests/e2e/conftest.py)
  - 21 additional Nexus A2A agents (from config/agents.json)
  - 8 Nexus interop gateways (FHIR, HL7v2, X12, NCPDP, DICOM, CDA)
  - 14 BulletTrain external systems (EHR, pharmacy, insurance, etc.)

Every agent points to a real Nexus on-demand gateway endpoint.
No mocks, no stubs.
"""

from __future__ import annotations

import logging
import os
import uuid

import httpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger("seed_full_registry")

GHARRA_BASE_URL = os.getenv("GHARRA_BASE_URL", "http://localhost:8400")
NEXUS_BASE = "http://nexus-gateway:8100"

# All agents to register, grouped by source
ALL_AGENTS = [
    # ── Canonical e2e agents (already seeded by seed.py, included for completeness)
    {"agent_id": "gharra://ie/agents/triage-e2e", "display_name": "Triage Agent", "jurisdiction": "IE", "alias": "triage",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc", "fhir-r4"], "fhir_r4": True, "stream_resume": True},
     "trust": {"jwks_uri": "https://triage.ie/.well-known/jwks.json", "mtls_required": True, "token_binding": "dpop", "cert_thumbprints": ["sha256:abc123"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": False, "data_classification": "confidential", "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://gb/agents/referral-e2e", "display_name": "Referral Agent", "jurisdiction": "GB", "alias": "diagnosis",
     "capabilities": {"protocols": ["http-rest", "fhir-r4"], "fhir_r4": True},
     "policy_tags": {"residency": ["GB", "EU"], "phi_allowed": True, "data_classification": "restricted", "purpose_of_use": ["treatment", "research"]}},
    {"agent_id": "gharra://us/agents/radiology-e2e", "display_name": "Radiology AI", "jurisdiction": "US", "alias": "imaging",
     "capabilities": {"protocols": ["http-rest", "fhir-r4"], "fhir_r4": True},
     "policy_tags": {"residency": ["US"], "prohibited_regions": ["CN", "RU"], "phi_allowed": True}},
    {"agent_id": "gharra://de/agents/pathology-e2e", "display_name": "Pathology Analyzer", "jurisdiction": "DE", "alias": "pharmacy",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "fhir_r4": False, "stream_resume": True},
     "policy_tags": {"residency": ["EU", "DE"], "phi_allowed": False}},

    # ── Nexus helixcare agents
    {"agent_id": "gharra://ie/agents/primary-care", "display_name": "Primary Care Agent", "jurisdiction": "IE", "alias": "primary_care",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["primary-care"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://gb/agents/specialty-care", "display_name": "Specialty Care Agent", "jurisdiction": "GB", "alias": "specialty_care",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["specialty-referral"]},
     "policy_tags": {"residency": ["GB", "EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://ie/agents/telehealth", "display_name": "Telehealth Agent", "jurisdiction": "IE", "alias": "telehealth",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["telemedicine-session"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://ie/agents/home-visit", "display_name": "Home Visit Agent", "jurisdiction": "IE", "alias": "home_visit",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["home-care"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://ie/agents/ccm", "display_name": "Chronic Care Management Agent", "jurisdiction": "IE", "alias": "ccm",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["chronic-care"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://ie/agents/clinician-avatar", "display_name": "Clinician Avatar Agent", "jurisdiction": "IE", "alias": "clinician_avatar",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["clinical-interview"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://ie/agents/triage-agent", "display_name": "ED Triage Agent", "jurisdiction": "IE", "alias": "triage",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["clinical-triage"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": False, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://gb/agents/diagnosis-agent", "display_name": "Diagnosis Agent", "jurisdiction": "GB", "alias": "diagnosis",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["clinical-diagnosis"]},
     "policy_tags": {"residency": ["GB", "EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://ie/agents/openhie-mediator", "display_name": "OpenHIE Mediator", "jurisdiction": "IE", "alias": "openhie_mediator",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc", "fhir-r4"], "domain": ["interoperability"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": False, "purpose_of_use": ["operations"]}},
    {"agent_id": "gharra://us/agents/imaging-agent", "display_name": "Imaging Agent", "jurisdiction": "US", "alias": "imaging",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["radiology-imaging"]},
     "policy_tags": {"residency": ["US"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://de/agents/pharmacy-agent", "display_name": "Pharmacy Agent", "jurisdiction": "DE", "alias": "pharmacy",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["pharmacy-dispensing"]},
     "policy_tags": {"residency": ["EU", "DE"], "phi_allowed": False, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://ie/agents/bed-manager", "display_name": "Bed Manager Agent", "jurisdiction": "IE", "alias": "bed_manager",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["bed-management"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": False, "purpose_of_use": ["operations"]}},
    {"agent_id": "gharra://gb/agents/discharge-agent", "display_name": "Discharge Agent", "jurisdiction": "GB", "alias": "discharge",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["discharge-planning"]},
     "policy_tags": {"residency": ["GB", "EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://ie/agents/followup", "display_name": "Followup Scheduler", "jurisdiction": "IE", "alias": "followup",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["followup-scheduling"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": False, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://ie/agents/coordinator", "display_name": "Care Coordinator", "jurisdiction": "IE", "alias": "coordinator",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["care-coordination"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": False, "purpose_of_use": ["treatment", "operations"]}},

    # ── Nexus telemed_scribe agents
    {"agent_id": "gharra://gb/agents/transcriber", "display_name": "Transcriber Agent", "jurisdiction": "GB", "alias": "transcriber",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["transcription"]},
     "policy_tags": {"residency": ["GB", "EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://gb/agents/summariser", "display_name": "Summariser Agent", "jurisdiction": "GB", "alias": "summariser",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["clinical-summary"]},
     "policy_tags": {"residency": ["GB", "EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://gb/agents/ehr-writer", "display_name": "EHR Writer Agent", "jurisdiction": "GB", "alias": "ehr_writer",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["ehr-documentation"]},
     "policy_tags": {"residency": ["GB", "EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},

    # ── Nexus consent_verification agents
    {"agent_id": "gharra://us/agents/insurer", "display_name": "Insurer Agent", "jurisdiction": "US", "alias": "insurer",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["insurance-auth"]},
     "policy_tags": {"residency": ["US"], "phi_allowed": False, "purpose_of_use": ["payment"]}},
    {"agent_id": "gharra://gb/agents/provider", "display_name": "Provider Agent", "jurisdiction": "GB", "alias": "provider",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["provider-workflow"]},
     "policy_tags": {"residency": ["GB", "EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://gb/agents/consent-analyser", "display_name": "Consent Analyser", "jurisdiction": "GB", "alias": "consent_analyser",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["consent-analysis"]},
     "policy_tags": {"residency": ["GB", "EU"], "phi_allowed": False, "purpose_of_use": ["operations"]}},
    {"agent_id": "gharra://gb/agents/hitl-ui", "display_name": "HITL UI Agent", "jurisdiction": "GB", "alias": "hitl_ui",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["human-in-the-loop"]},
     "policy_tags": {"residency": ["GB", "EU"], "phi_allowed": False, "purpose_of_use": ["operations"]}},

    # ── Nexus public_health_surveillance agents
    {"agent_id": "gharra://ie/agents/hospital-reporter", "display_name": "Hospital Reporter", "jurisdiction": "IE", "alias": "hospital_reporter",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["outbreak-reporting"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": False, "purpose_of_use": ["public_health"]}},
    {"agent_id": "gharra://ie/agents/osint", "display_name": "OSINT Agent", "jurisdiction": "IE", "alias": "osint",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["intelligence"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": False, "purpose_of_use": ["public_health"]}},
    {"agent_id": "gharra://ie/agents/central-surveillance", "display_name": "Central Surveillance", "jurisdiction": "IE", "alias": "central_surveillance",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["surveillance-coordination"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": False, "purpose_of_use": ["public_health"]}},

    # ── Nexus interop gateway agents
    {"agent_id": "gharra://ie/agents/profile-registry", "display_name": "Profile Registry Agent", "jurisdiction": "IE", "alias": "profile_registry",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["profile-discovery"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": False, "purpose_of_use": ["operations"]}},
    {"agent_id": "gharra://ie/agents/fhir-profile", "display_name": "FHIR Profile Agent", "jurisdiction": "IE", "alias": "fhir_profile",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc", "fhir-r4"], "fhir_r4": True, "domain": ["fhir-gateway"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": True, "purpose_of_use": ["treatment", "operations"]}},
    {"agent_id": "gharra://us/agents/x12-gateway", "display_name": "X12 Gateway Agent", "jurisdiction": "US", "alias": "x12_gateway",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["x12-edi"]},
     "policy_tags": {"residency": ["US"], "phi_allowed": False, "purpose_of_use": ["payment"]}},
    {"agent_id": "gharra://us/agents/ncpdp-gateway", "display_name": "NCPDP Gateway Agent", "jurisdiction": "US", "alias": "ncpdp_gateway",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["ncpdp-pharmacy"]},
     "policy_tags": {"residency": ["US"], "phi_allowed": False, "purpose_of_use": ["payment"]}},
    {"agent_id": "gharra://ie/agents/audit-agent", "display_name": "Audit Agent", "jurisdiction": "IE", "alias": "audit",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["audit-compliance"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": False, "purpose_of_use": ["operations"]}},
    {"agent_id": "gharra://gb/agents/hl7v2-gateway", "display_name": "HL7v2 Gateway Agent", "jurisdiction": "GB", "alias": "hl7v2_gateway",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["hl7v2-legacy"]},
     "policy_tags": {"residency": ["GB", "EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://gb/agents/cda-document", "display_name": "CDA Document Agent", "jurisdiction": "GB", "alias": "cda_document",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["cda-generation"]},
     "policy_tags": {"residency": ["GB", "EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://us/agents/dicom-imaging", "display_name": "DICOM Imaging Agent", "jurisdiction": "US", "alias": "dicom_imaging",
     "capabilities": {"protocols": ["nexus-a2a-jsonrpc"], "domain": ["dicom-metadata"]},
     "policy_tags": {"residency": ["US"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},

    # ── BulletTrain external systems (registered as GHARRA agents)
    {"agent_id": "gharra://ie/agents/bt-ambulance-ems", "display_name": "Ambulance EMS", "jurisdiction": "IE", "alias": "ambulance_ems",
     "capabilities": {"protocols": ["http-rest"], "domain": ["emergency-transport"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://ie/agents/bt-analytics-bi", "display_name": "Analytics BI", "jurisdiction": "IE", "alias": "analytics_bi",
     "capabilities": {"protocols": ["http-rest"], "domain": ["analytics"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": False, "purpose_of_use": ["operations"]}},
    {"agent_id": "gharra://gb/agents/bt-ehr-hims", "display_name": "EHR/HIMS", "jurisdiction": "GB", "alias": "ehr_hims",
     "capabilities": {"protocols": ["http-rest", "fhir-r4"], "fhir_r4": True, "domain": ["ehr"]},
     "policy_tags": {"residency": ["GB", "EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://us/agents/bt-insurance-eclaims", "display_name": "Insurance eClaims", "jurisdiction": "US", "alias": "insurance_eclaims",
     "capabilities": {"protocols": ["http-rest", "x12"], "domain": ["claims-processing"]},
     "policy_tags": {"residency": ["US"], "phi_allowed": False, "purpose_of_use": ["payment"]}},
    {"agent_id": "gharra://de/agents/bt-pharmacy-system", "display_name": "Pharmacy System", "jurisdiction": "DE", "alias": "pharmacy_system",
     "capabilities": {"protocols": ["http-rest"], "domain": ["pharmacy-management"]},
     "policy_tags": {"residency": ["EU", "DE"], "phi_allowed": False, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://gb/agents/bt-lis", "display_name": "Laboratory Information System", "jurisdiction": "GB", "alias": "lis",
     "capabilities": {"protocols": ["http-rest", "hl7v2"], "domain": ["laboratory"]},
     "policy_tags": {"residency": ["GB", "EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://us/agents/bt-pacs-ris", "display_name": "PACS/RIS", "jurisdiction": "US", "alias": "pacs_ris",
     "capabilities": {"protocols": ["http-rest", "dicom"], "domain": ["radiology-pacs"]},
     "policy_tags": {"residency": ["US"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://ie/agents/bt-sms-whatsapp", "display_name": "SMS/WhatsApp Gateway", "jurisdiction": "IE", "alias": "sms_whatsapp",
     "capabilities": {"protocols": ["http-rest"], "domain": ["messaging"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": False, "purpose_of_use": ["operations"]}},
    {"agent_id": "gharra://ie/agents/bt-telemedicine", "display_name": "Telemedicine Platform", "jurisdiction": "IE", "alias": "telemedicine_ext",
     "capabilities": {"protocols": ["http-rest"], "domain": ["telemedicine"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://ie/agents/bt-erp", "display_name": "Enterprise Resource Planning", "jurisdiction": "IE", "alias": "erp",
     "capabilities": {"protocols": ["http-rest"], "domain": ["enterprise-resource"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": False, "purpose_of_use": ["operations"]}},
    {"agent_id": "gharra://ie/agents/bt-supply-chain", "display_name": "Supply Chain ERP", "jurisdiction": "IE", "alias": "supply_chain_erp",
     "capabilities": {"protocols": ["http-rest"], "domain": ["supply-chain"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": False, "purpose_of_use": ["operations"]}},
    {"agent_id": "gharra://gb/agents/bt-terminology", "display_name": "Terminology Service", "jurisdiction": "GB", "alias": "terminology_service",
     "capabilities": {"protocols": ["http-rest", "fhir-r4"], "fhir_r4": True, "domain": ["terminology"]},
     "policy_tags": {"residency": ["GB", "EU"], "phi_allowed": False, "purpose_of_use": ["operations"]}},
    {"agent_id": "gharra://ie/agents/bt-patient-portal", "display_name": "Patient Portal", "jurisdiction": "IE", "alias": "patient_portal",
     "capabilities": {"protocols": ["http-rest"], "domain": ["patient-engagement"]},
     "policy_tags": {"residency": ["EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
    {"agent_id": "gharra://gb/agents/bt-provider-portal", "display_name": "Provider Portal", "jurisdiction": "GB", "alias": "provider_portal",
     "capabilities": {"protocols": ["http-rest"], "domain": ["provider-engagement"]},
     "policy_tags": {"residency": ["GB", "EU"], "phi_allowed": True, "purpose_of_use": ["treatment"]}},
]


def seed_full_registry(base_url: str | None = None) -> dict[str, int]:
    """Register all agents in GHARRA. Returns counts."""
    base = (base_url or GHARRA_BASE_URL).rstrip("/")
    created = 0
    existing = 0
    failed = 0

    with httpx.Client(base_url=base, timeout=15.0) as client:
        for agent in ALL_AGENTS:
            body = {
                "agent_id": agent["agent_id"],
                "display_name": agent["display_name"],
                "jurisdiction": agent["jurisdiction"],
                "endpoints": [{
                    "url": f"{NEXUS_BASE}/rpc/{agent['alias']}",
                    "protocol": agent["capabilities"]["protocols"][0],
                    "priority": 10,
                    "weight": 100,
                }],
                "capabilities": agent.get("capabilities", {}),
                "policy_tags": agent.get("policy_tags", {}),
            }
            if "trust" in agent:
                body["trust"] = agent["trust"]

            resp = client.post(
                "/v1/agents",
                json=body,
                headers={"X-Idempotency-Key": str(uuid.uuid4())},
            )
            if resp.status_code == 201:
                created += 1
                logger.info("Created  %-35s %s", agent["display_name"], agent["agent_id"])
            elif resp.status_code == 409:
                existing += 1
            else:
                failed += 1
                logger.warning("Failed   %-35s %d: %s", agent["display_name"], resp.status_code, resp.text[:100])

    total = created + existing
    logger.info("Seed complete: %d total (%d created, %d existing, %d failed)", total, created, existing, failed)
    return {"total": total, "created": created, "existing": existing, "failed": failed}


if __name__ == "__main__":
    result = seed_full_registry()
    print(f"Total: {result['total']}, Created: {result['created']}, Existing: {result['existing']}, Failed: {result['failed']}")
