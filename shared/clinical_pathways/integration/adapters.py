"""Adapters that convert PersonalisedPathway to BulletTrain agent input formats.

Each adapter is a pure function: PersonalisedPathway → dict that matches the
downstream agent's expected input contract.  No network calls — these are
structural transformers that can be tested in isolation.
"""

from __future__ import annotations

import logging
from typing import Any

from ..engine.deviation import DeviationRegister, DeviationSeverity
from ..engine.models import (
    ConfidenceLevel,
    ModificationType,
    PersonalisedActivity,
    PersonalisedPathway,
)

logger = logging.getLogger(__name__)


# ── Prompt-engineering context helpers ──────────────────────────────────

def _build_reasoning_hint(pathway: PersonalisedPathway) -> str:
    """Suggest which reasoning mode the downstream agent should use."""
    confidence = pathway.explainability.confidence
    safety_warnings = pathway.explainability.safety_warnings
    has_safety_overrides = any(
        m.modification_type == ModificationType.SAFETY_OVERRIDE
        for m in pathway.explainability.modifications
    )

    if (
        confidence == ConfidenceLevel.REQUIRES_CLINICIAN_REVIEW
        or len(safety_warnings) >= 3
    ):
        return "clinical_reasoning with adversarial_thinking"
    if confidence == ConfidenceLevel.LOW:
        return "clinical_reasoning with failure_analysis"
    if has_safety_overrides:
        return "scientific_method"
    return "clinical_reasoning"


def _build_recommended_clauses(pathway: PersonalisedPathway) -> list[str]:
    """List clause names to activate for the downstream agent."""
    clauses = ["first_principles", "evidence_grounding"]
    confidence = pathway.explainability.confidence

    if confidence != ConfidenceLevel.HIGH:
        clauses.extend(["hidden_assumptions", "confidence_calibration"])
    if pathway.explainability.safety_warnings:
        clauses.append("counter_arguments")
    if pathway.explainability.modification_count > 3:
        clauses.append("scenario_reasoning")

    return clauses


def _build_evidence_citations(pathway: PersonalisedPathway) -> list[dict[str, str]]:
    """Build citation entries from the deviation register."""
    if pathway.deviation_register is None:
        return []

    # Try to extract a fallback guideline reference from governance metadata
    governance_ref = "See pathway governance metadata"

    citations: list[dict[str, str]] = []
    for d in pathway.deviation_register.deviations:
        citations.append({
            "deviation_id": d.deviation_id,
            "guideline_reference": (
                d.evidence_reference if d.evidence_reference else governance_ref
            ),
            "rule_applied": d.modification_type.value,
        })
    return citations


# ── Diagnostic Reasoning Agent ──────────────────────────────────────────

def to_diagnostic_context(
    pathway: PersonalisedPathway,
    *,
    patient_id: str = "",
    chief_complaint: str = "",
) -> dict[str, Any]:
    """Build DiagnosticReasoningAgent.handle_request() context dict.

    Maps pathway urgency and safety state to strategy selection:
      - SAFETY_OVERRIDE or CRITICAL deviations → dual_agent strategy
      - URGENCY_ELEVATED → chain_of_thought with elevated priority
      - Standard → chain_of_thought
    """
    # Determine strategy based on pathway safety state
    has_safety_override = any(
        m.modification_type == ModificationType.SAFETY_OVERRIDE
        for m in pathway.explainability.modifications
    )
    has_critical_deviations = (
        pathway.deviation_register is not None
        and any(
            d.severity == DeviationSeverity.CRITICAL
            for d in pathway.deviation_register.deviations
        )
    )
    has_urgency_elevation = any(
        m.modification_type == ModificationType.URGENCY_ELEVATED
        for m in pathway.explainability.modifications
    )

    if has_safety_override or has_critical_deviations:
        strategy = "dual_agent"
    elif has_urgency_elevation:
        strategy = "chain_of_thought"
    else:
        strategy = "chain_of_thought"

    # Build active conditions from pathway context summary
    active_conditions = pathway.explainability.context_summary.get("active_conditions", [])

    # Collect non-excluded activities as diagnostic guidance
    active_activities = []
    for node in pathway.nodes:
        for act in node.activities:
            if not act.is_excluded:
                active_activities.append({
                    "activity_id": act.activity_id,
                    "name": act.name,
                    "category": act.category,
                    "urgency": act.urgency,
                })

    return {
        "intent": "diagnose",
        "context": {
            "patient_id": patient_id or pathway.patient_id,
            "chief_complaint": chief_complaint,
            "pathway_id": pathway.pathway_id,
            "pathway_title": pathway.pathway_title,
            "active_conditions": active_conditions,
            "safety_warnings": pathway.explainability.safety_warnings,
            "confidence": pathway.explainability.confidence.value,
            "clinician_override_recommended": pathway.explainability.clinician_override_recommended,
            "personalised_activities": active_activities,
            "modification_count": pathway.explainability.modification_count,
        },
        "patient_id": patient_id or pathway.patient_id,
        "strategy": strategy,
        "reasoning_hint": _build_reasoning_hint(pathway),
        "recommended_clauses": _build_recommended_clauses(pathway),
        "evidence_citations": _build_evidence_citations(pathway),
    }


# ── Treatment Recommendation Agent ─────────────────────────────────────

def to_treatment_context(
    pathway: PersonalisedPathway,
    *,
    diagnosis: str = "",
    specialty: str = "",
) -> dict[str, Any]:
    """Build TreatmentRecommendationAgent.recommend() context dict.

    Embeds contraindication flags and deviation register so the treatment
    agent respects pathway-driven medication exclusions.
    """
    # Collect contraindicated medications
    contraindicated = []
    excluded_activities = []
    for node in pathway.nodes:
        for act in node.activities:
            if act.is_excluded:
                excluded_activities.append({
                    "activity_id": act.activity_id,
                    "name": act.name,
                    "exclusion_reason": act.exclusion_reason,
                })
            for mod in act.modifications:
                if mod.modification_type == ModificationType.CONTRAINDICATION_FLAGGED:
                    contraindicated.append({
                        "activity_id": act.activity_id,
                        "medication": act.name,
                        "reason": mod.reason,
                        "evidence": mod.evidence_reference,
                    })

    # Build deviation summary for treatment awareness
    deviation_summary = None
    if pathway.deviation_register is not None:
        dev_reg = pathway.deviation_register
        deviation_summary = {
            "total_deviations": dev_reg.total_deviations,
            "severity_summary": dev_reg.deviation_severity_summary,
            "requires_clinician_signoff": dev_reg.requires_any_clinician_signoff,
            "major_deviations": [
                {
                    "deviation_id": d.deviation_id,
                    "standard_step": d.standard_pathway_step,
                    "individualised_step": d.individualised_step,
                    "reason": d.reason,
                }
                for d in dev_reg.deviations
                if d.severity in (DeviationSeverity.MAJOR, DeviationSeverity.CRITICAL)
            ],
        }

    return {
        "diagnosis": diagnosis,
        "specialty": specialty,
        "patient_context": {
            "pathway_id": pathway.pathway_id,
            "patient_id": pathway.patient_id,
            "confidence": pathway.explainability.confidence.value,
            "contraindicated_medications": contraindicated,
            "excluded_activities": excluded_activities,
            "safety_warnings": pathway.explainability.safety_warnings,
            "deviation_summary": deviation_summary,
            "context_summary": pathway.explainability.context_summary,
            "reasoning_chain": pathway.explainability.reasoning_chain,
        },
        "reasoning_hint": _build_reasoning_hint(pathway),
        "recommended_clauses": _build_recommended_clauses(pathway),
        "evidence_citations": _build_evidence_citations(pathway),
    }


# ── Safe Prescribing Agent ──────────────────────────────────────────────

def to_prescribing_guard(
    pathway: PersonalisedPathway,
    *,
    medication_name: str,
    dose_mg: int,
    frequency: str,
    patient_id: str = "",
) -> dict[str, Any]:
    """Build prescribing guard check from pathway contraindications.

    Returns a dict with the medication order and pathway-driven exclusion
    flags that the SafePrescribingAgent should check before prescribing.
    """
    # Check if this medication is excluded by the pathway
    is_excluded = False
    exclusion_reason = ""
    for node in pathway.nodes:
        for act in node.activities:
            if act.is_excluded and medication_name.lower() in act.name.lower():
                is_excluded = True
                exclusion_reason = act.exclusion_reason
                break

    # Check contraindication modifications
    contraindication_flags = []
    for mod in pathway.explainability.modifications:
        if mod.modification_type == ModificationType.CONTRAINDICATION_FLAGGED:
            contraindication_flags.append({
                "description": mod.description,
                "reason": mod.reason,
                "evidence": mod.evidence_reference,
            })

    return {
        "order": {
            "patient_id": patient_id or pathway.patient_id,
            "medication_name": medication_name,
            "dose_mg": dose_mg,
            "frequency": frequency,
        },
        "pathway_guard": {
            "pathway_id": pathway.pathway_id,
            "is_excluded_by_pathway": is_excluded,
            "exclusion_reason": exclusion_reason,
            "contraindication_flags": contraindication_flags,
            "confidence": pathway.explainability.confidence.value,
            "requires_clinician_review": pathway.explainability.clinician_override_recommended,
        },
    }


# ── Referral Agent ──────────────────────────────────────────────────────

def to_referral_request(
    pathway: PersonalisedPathway,
    *,
    patient_id: str = "",
    encounter_id: str = "",
) -> dict[str, Any]:
    """Build ReferralAgent.draft_referral() input from pathway activities.

    Extracts activities with required_agent_capability to determine
    which specialist referrals the pathway requires.
    """
    referrals = []
    for node in pathway.nodes:
        for act in node.activities:
            if act.required_agent_capability and not act.is_excluded:
                # Determine urgency from pathway modifications
                urgency = act.urgency
                for mod in act.modifications:
                    if mod.modification_type == ModificationType.URGENCY_ELEVATED:
                        urgency = "urgent"

                referrals.append({
                    "specialty": act.required_agent_capability,
                    "activity_id": act.activity_id,
                    "activity_name": act.name,
                    "urgency": urgency,
                    "clinical_summary": _build_referral_summary(pathway, act),
                })

    return {
        "patient_id": patient_id or pathway.patient_id,
        "encounter_id": encounter_id,
        "pathway_id": pathway.pathway_id,
        "referrals": referrals,
        "deviation_register_id": (
            pathway.deviation_register.register_id
            if pathway.deviation_register else ""
        ),
    }


def _build_referral_summary(
    pathway: PersonalisedPathway,
    activity: PersonalisedActivity,
) -> str:
    """Build clinical summary for a referral from pathway context."""
    parts = [
        f"Referral generated from pathway: {pathway.pathway_title}.",
        f"Activity: {activity.name}.",
    ]
    if activity.modifications:
        parts.append("Modifications:")
        for mod in activity.modifications:
            parts.append(f"  - {mod.description} ({mod.reason})")
    if pathway.explainability.safety_warnings:
        parts.append(f"Safety warnings: {'; '.join(pathway.explainability.safety_warnings)}")
    return " ".join(parts)


# ── Investigation Planner Agent ─────────────────────────────────────────

def to_investigation_plan(
    pathway: PersonalisedPathway,
    *,
    guideline_topic: str = "",
) -> dict[str, Any]:
    """Build InvestigationPlannerAgent.draft_plan() input.

    Extracts investigation/monitoring activities from the personalised
    pathway and marks contraindicated investigations.
    """
    investigations = []
    for node in pathway.nodes:
        for act in node.activities:
            if act.category in ("investigation", "monitoring", "assessment"):
                investigations.append({
                    "activity_id": act.activity_id,
                    "name": act.name,
                    "category": act.category,
                    "is_excluded": act.is_excluded,
                    "exclusion_reason": act.exclusion_reason,
                    "urgency": act.urgency,
                    "modifications": [
                        {
                            "type": m.modification_type.value,
                            "description": m.description,
                            "reason": m.reason,
                        }
                        for m in act.modifications
                    ],
                })

    return {
        "patient_context": {
            "patient_id": pathway.patient_id,
            "pathway_id": pathway.pathway_id,
            "context_summary": pathway.explainability.context_summary,
        },
        "guideline_topic": guideline_topic or pathway.pathway_title,
        "pathway_investigations": investigations,
        "contraindication_flags": [
            m.description
            for m in pathway.explainability.modifications
            if m.modification_type == ModificationType.CONTRAINDICATION_FLAGGED
        ],
    }


# ── Imaging Agent ───────────────────────────────────────────────────────

def to_imaging_request(
    pathway: PersonalisedPathway,
    *,
    patient_id: str = "",
    modality: str = "",
) -> dict[str, Any]:
    """Build ImagingAgent input with pathway contraindication checks.

    Filters imaging activities from the pathway and flags any that are
    contraindicated.
    """
    imaging_activities = []
    for node in pathway.nodes:
        for act in node.activities:
            if act.category in ("imaging", "investigation") and "imag" in act.name.lower():
                imaging_activities.append({
                    "activity_id": act.activity_id,
                    "name": act.name,
                    "is_excluded": act.is_excluded,
                    "exclusion_reason": act.exclusion_reason,
                    "urgency": act.urgency,
                })

    return {
        "patient_id": patient_id or pathway.patient_id,
        "modality": modality,
        "pathway_id": pathway.pathway_id,
        "pathway_imaging_activities": imaging_activities,
        "contraindication_flags": [
            m.description
            for m in pathway.explainability.modifications
            if m.modification_type == ModificationType.CONTRAINDICATION_FLAGGED
        ],
    }


# ── Discharge Agent ─────────────────────────────────────────────────────

def to_discharge_plan(
    pathway: PersonalisedPathway,
) -> dict[str, Any]:
    """Build DischargeAgent.plan_discharge() input.

    Incorporates follow-up adaptations from the pathway, including
    modified monitoring schedules and transport adaptations.
    """
    follow_up_modifications = []
    for mod in pathway.explainability.modifications:
        if mod.modification_type == ModificationType.FOLLOW_UP_ADAPTED:
            follow_up_modifications.append({
                "description": mod.description,
                "reason": mod.reason,
                "evidence": mod.evidence_reference,
            })

    # Collect non-excluded activities for discharge planning
    discharge_activities = []
    for node in pathway.nodes:
        for act in node.activities:
            if not act.is_excluded:
                discharge_activities.append({
                    "activity_id": act.activity_id,
                    "name": act.name,
                    "category": act.category,
                    "urgency": act.urgency,
                    "sequence_order": act.sequence_order,
                })

    return {
        "patient": {
            "patient_id": pathway.patient_id,
        },
        "pathway_context": {
            "pathway_id": pathway.pathway_id,
            "pathway_title": pathway.pathway_title,
            "encounter_journey_summary": pathway.encounter_journey_summary,
            "follow_up_modifications": follow_up_modifications,
            "discharge_activities": discharge_activities,
            "safety_warnings": pathway.explainability.safety_warnings,
            "confidence": pathway.explainability.confidence.value,
        },
    }


# ── Continuity Agent ────────────────────────────────────────────────────

def to_continuity_request(
    pathway: PersonalisedPathway,
    *,
    task_type: str = "follow_up",
    patient_id: str = "",
) -> dict[str, Any]:
    """Build ContinuityAgent.handle_request() input.

    Reads monitoring schedule changes and intensity modifications from
    the personalised pathway to set follow-up parameters.
    """
    # Collect monitoring modifications
    monitoring_changes = []
    for mod in pathway.explainability.modifications:
        if mod.modification_type in (
            ModificationType.FOLLOW_UP_ADAPTED,
            ModificationType.INTENSITY_INCREASED,
            ModificationType.INTENSITY_REDUCED,
        ):
            monitoring_changes.append({
                "type": mod.modification_type.value,
                "description": mod.description,
                "reason": mod.reason,
            })

    return {
        "task_type": task_type,
        "patient_id": patient_id or pathway.patient_id,
        "context": {
            "pathway_id": pathway.pathway_id,
            "pathway_title": pathway.pathway_title,
            "monitoring_changes": monitoring_changes,
            "modification_count": pathway.explainability.modification_count,
            "confidence": pathway.explainability.confidence.value,
            "context_summary": pathway.explainability.context_summary,
        },
    }


# ── Chat Assistant ──────────────────────────────────────────────────────

def to_chat_context(
    pathway: PersonalisedPathway,
) -> dict[str, Any]:
    """Build ChatAssistant pathway-aware context injection.

    Provides the chat assistant with pathway personalisation state so it
    can answer clinician questions about the patient's individualised plan.
    """
    deviation_info = None
    if pathway.deviation_register is not None:
        dev_reg = pathway.deviation_register
        deviation_info = {
            "total_deviations": dev_reg.total_deviations,
            "severity_summary": dev_reg.deviation_severity_summary,
            "requires_clinician_signoff": dev_reg.requires_any_clinician_signoff,
            "deviations": [
                {
                    "id": d.deviation_id,
                    "standard_step": d.standard_pathway_step,
                    "individualised_step": d.individualised_step,
                    "reason": d.reason,
                    "severity": d.severity.value,
                }
                for d in dev_reg.deviations
            ],
        }

    return {
        "pathway_personalisation": {
            "pathway_id": pathway.pathway_id,
            "pathway_title": pathway.pathway_title,
            "patient_id": pathway.patient_id,
            "personalised_at": pathway.personalised_at.isoformat(),
            "encounter_journey_summary": pathway.encounter_journey_summary,
            "modification_count": pathway.explainability.modification_count,
            "confidence": pathway.explainability.confidence.value,
            "safety_warnings": pathway.explainability.safety_warnings,
            "clinician_override_recommended": pathway.explainability.clinician_override_recommended,
            "reasoning_chain": pathway.explainability.reasoning_chain,
            "deviation_register": deviation_info,
        },
        "reasoning_hint": _build_reasoning_hint(pathway),
        "recommended_clauses": _build_recommended_clauses(pathway),
        "evidence_citations": _build_evidence_citations(pathway),
    }


# ── APEX Risk Stratification ───────────────────────────────────────────

def to_apex_risk_input(
    pathway: PersonalisedPathway,
    *,
    patient_id: str = "",
) -> dict[str, Any]:
    """Build APEX risk stratification input from pathway confidence.

    Feeds pathway personalisation confidence back into the risk model
    so that low-confidence pathways trigger higher risk scores.
    """
    # Map pathway confidence to numeric risk modifier
    confidence_risk_map = {
        ConfidenceLevel.HIGH: 0.0,
        ConfidenceLevel.MEDIUM: 0.15,
        ConfidenceLevel.LOW: 0.35,
        ConfidenceLevel.REQUIRES_CLINICIAN_REVIEW: 0.50,
    }
    risk_modifier = confidence_risk_map.get(
        pathway.explainability.confidence, 0.0
    )

    return {
        "patient_id": patient_id or pathway.patient_id,
        "predictors": {
            "pathway_confidence": pathway.explainability.confidence.value,
            "pathway_confidence_risk_modifier": risk_modifier,
            "modification_count": pathway.explainability.modification_count,
            "safety_warning_count": len(pathway.explainability.safety_warnings),
            "has_contraindications": any(
                m.modification_type == ModificationType.CONTRAINDICATION_FLAGGED
                for m in pathway.explainability.modifications
            ),
            "has_safety_overrides": any(
                m.modification_type == ModificationType.SAFETY_OVERRIDE
                for m in pathway.explainability.modifications
            ),
            "deviation_count": (
                pathway.deviation_register.total_deviations
                if pathway.deviation_register else 0
            ),
            "requires_clinician_signoff": (
                pathway.deviation_register.requires_any_clinician_signoff
                if pathway.deviation_register else False
            ),
        },
    }
