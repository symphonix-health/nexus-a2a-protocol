"""Agent cards for registration in the Global Agent Registry (GHARRA).

These define the Pathway Knowledge Agent and Pathway Personalisation Agent
as discoverable capabilities in the A2A ecosystem.
"""

from __future__ import annotations

PATHWAY_KNOWLEDGE_AGENT_CARD = {
    "agent_id": "pathway-knowledge-agent",
    "name": "Pathway Knowledge Agent",
    "description": (
        "Stores and retrieves nationally approved clinical pathways as structured "
        "FHIR PlanDefinition-style resources.  Supports pathway discovery by "
        "country, authority, condition, and keyword search."
    ),
    "version": "0.1.0",
    "provider": "Symphonix-Health",
    "capabilities": [
        {
            "capability_id": "pathway-retrieval",
            "name": "Clinical Pathway Retrieval",
            "description": "Retrieve approved pathway definitions by ID, country, or authority",
            "clinical_domains": ["all"],
            "input_fhir_resources": [],
            "output_fhir_resources": ["PlanDefinition"],
        },
        {
            "capability_id": "pathway-search",
            "name": "Clinical Pathway Search",
            "description": "Search pathway definitions by keyword or condition",
            "clinical_domains": ["all"],
            "input_fhir_resources": [],
            "output_fhir_resources": ["PlanDefinition"],
        },
    ],
    "supported_pathways": [
        "nice-ng106-heart-failure",
        "nice-ng115-copd",
        "nice-ng28-diabetes-type2",
        "nice-ng51-sepsis",
        "who-maternal-anc",
    ],
    "interoperability": {
        "protocol": "a2a",
        "transport": "http-rest",
        "data_format": "json",
        "fhir_version": "R4",
    },
    "trust_metadata": {
        "clinical_safety_certified": True,
        "audit_logging": True,
        "data_sovereignty": "GB",
    },
    "endpoints": {
        "base_url": "http://localhost:8500",
        "list_pathways": "/v1/pathways",
        "get_pathway": "/v1/pathways/{pathway_id}",
        "search_pathways": "/v1/pathways/search/{query}",
    },
}

PATHWAY_PERSONALISATION_AGENT_CARD = {
    "agent_id": "pathway-personalisation-agent",
    "name": "Pathway Personalisation Agent",
    "description": (
        "Takes a patient context object and a standard national pathway, applies "
        "personalisation rules (branching, exclusions, sequencing, intensity "
        "adjustments), and returns a tailored encounter journey with full "
        "explainability and audit trail.  Implements NICE NG56 multimorbidity "
        "guidance computationally."
    ),
    "version": "0.1.0",
    "provider": "Symphonix-Health",
    "capabilities": [
        {
            "capability_id": "pathway-personalisation",
            "name": "Pathway Personalisation",
            "description": (
                "Personalise a national clinical pathway based on patient context. "
                "Considers comorbidities, polypharmacy, allergies, renal function, "
                "frailty, social determinants, and clinical safety constraints."
            ),
            "clinical_domains": [
                "cardiology",
                "respiratory",
                "endocrinology",
                "infectious_disease",
                "obstetrics",
                "multimorbidity",
            ],
            "input_fhir_resources": [
                "Patient",
                "Condition",
                "MedicationRequest",
                "AllergyIntolerance",
                "Observation",
                "Encounter",
                "FamilyMemberHistory",
            ],
            "output_fhir_resources": ["CarePlan", "PlanDefinition"],
        },
        {
            "capability_id": "safety-guardrails",
            "name": "Clinical Safety Guardrails",
            "description": (
                "Cross-checks pathway activities against allergies, drug interactions, "
                "contraindications, and critical lab values"
            ),
            "clinical_domains": ["pharmacology", "patient_safety"],
            "input_fhir_resources": [
                "AllergyIntolerance",
                "MedicationRequest",
                "Observation",
            ],
            "output_fhir_resources": [],
        },
    ],
    "personalisation_rules": [
        "polypharmacy_medication_review",
        "frailty_intensity_adjustment",
        "recurrent_admissions",
        "language_barrier_adaptation",
        "transport_barrier_followup",
        "hf_ckd_renal_safe",
        "hf_polypharmacy_review",
        "copd_chf_comorbidity",
        "copd_frequent_exacerbations",
        "dm2_renal_impairment",
        "dm2_foot_ulcer_mdl",
        "sepsis_immunocompromised",
        "sepsis_penicillin_allergy",
        "sepsis_hf_cautious_fluids",
        "anc_advanced_maternal_age",
        "anc_pre_eclampsia_history",
    ],
    "interoperability": {
        "protocol": "a2a",
        "transport": "http-rest",
        "data_format": "json",
        "fhir_version": "R4",
    },
    "trust_metadata": {
        "clinical_safety_certified": True,
        "audit_logging": True,
        "explainability": True,
        "clinician_in_the_loop": True,
        "data_sovereignty": "GB",
    },
    "endpoints": {
        "base_url": "http://localhost:8500",
        "personalise": "/v1/pathways/personalise",
    },
}

CONTEXT_ASSEMBLER_AGENT_CARD = {
    "agent_id": "context-assembler-agent",
    "name": "Context Assembler Agent",
    "description": (
        "Consolidates FHIR resources (Condition, Encounter, Observation, "
        "MedicationStatement, AllergyIntolerance) into a computable patient "
        "portrait with risk flags.  Serves as the input contract for the "
        "Pathway Personalisation Agent."
    ),
    "version": "0.1.0",
    "provider": "Symphonix-Health",
    "capabilities": [
        {
            "capability_id": "context-assembly",
            "name": "Patient Context Assembly",
            "description": "Build a unified patient context from multiple FHIR data sources",
            "clinical_domains": ["all"],
            "input_fhir_resources": [
                "Patient",
                "Condition",
                "MedicationRequest",
                "AllergyIntolerance",
                "Observation",
                "Encounter",
                "Immunization",
                "FamilyMemberHistory",
            ],
            "output_fhir_resources": [],
        },
    ],
    "interoperability": {
        "protocol": "a2a",
        "transport": "http-rest",
        "data_format": "json",
        "fhir_version": "R4",
    },
    "trust_metadata": {
        "clinical_safety_certified": True,
        "audit_logging": True,
        "consent_checking": True,
        "phi_redaction": True,
        "data_sovereignty": "GB",
    },
}


def get_all_agent_cards() -> list[dict]:
    """Return all agent cards for bulk registration."""
    return [
        PATHWAY_KNOWLEDGE_AGENT_CARD,
        PATHWAY_PERSONALISATION_AGENT_CARD,
        CONTEXT_ASSEMBLER_AGENT_CARD,
    ]
