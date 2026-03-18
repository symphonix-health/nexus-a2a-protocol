"""Rule-based personalisation rules.

Encodes clinical rules derived from NICE guidelines for pathway
personalisation.  Each rule is a callable that takes a PatientContext
and returns zero or more PathwayModifications.
"""

from __future__ import annotations

from typing import Sequence

from ..context.models import FrailtyScore, PatientContext
from .models import ModificationType, PathwayModification


# ── Rule registry ────────────────────────────────────────────────────

_RULES: list[tuple[str, type["PersonalisationRule"]]] = []


def register_rule(name: str):
    """Decorator to register a personalisation rule."""
    def decorator(cls: type[PersonalisationRule]):
        _RULES.append((name, cls))
        return cls
    return decorator


def get_all_rules() -> list[tuple[str, "PersonalisationRule"]]:
    return [(name, cls()) for name, cls in _RULES]


class PersonalisationRule:
    """Base class for personalisation rules."""

    def applies_to_pathway(self, pathway_id: str) -> bool:
        return True

    def evaluate(self, ctx: PatientContext, pathway_id: str) -> list[PathwayModification]:
        raise NotImplementedError


# ── Cross-pathway rules ─────────────────────────────────────────────

@register_rule("polypharmacy_medication_review")
class PolypharmacyMedicationReview(PersonalisationRule):
    """NICE NG56: Patients on ≥10 medicines should have medication review prioritised."""

    def evaluate(self, ctx: PatientContext, pathway_id: str) -> list[PathwayModification]:
        if not ctx.is_polypharmacy(threshold=10):
            return []
        return [
            PathwayModification(
                modification_type=ModificationType.SEQUENCE_CHANGED,
                description="Medication review moved to first step due to significant polypharmacy",
                reason=f"Patient is on {ctx.medication_count()} active medications (≥10 threshold per NICE NG56)",
                context_factors=["polypharmacy", f"medication_count:{ctx.medication_count()}"],
                evidence_reference="NICE NG56 — Multimorbidity",
            )
        ]


@register_rule("frailty_intensity_adjustment")
class FrailtyIntensityAdjustment(PersonalisationRule):
    """Frail patients may need intensity adjustments and community follow-up."""

    def evaluate(self, ctx: PatientContext, pathway_id: str) -> list[PathwayModification]:
        if ctx.frailty_score not in (FrailtyScore.MODERATE, FrailtyScore.SEVERE, FrailtyScore.VERY_SEVERE):
            return []
        mods = [
            PathwayModification(
                modification_type=ModificationType.FOLLOW_UP_ADAPTED,
                description="Follow-up adapted to community-based monitoring due to frailty",
                reason=f"Patient frailty score: {ctx.frailty_score.value}",
                context_factors=["frailty", f"frailty_score:{ctx.frailty_score.value}"],
                evidence_reference="NICE NG56, NHS England Frailty Framework",
            )
        ]
        if ctx.frailty_score in (FrailtyScore.SEVERE, FrailtyScore.VERY_SEVERE):
            mods.append(
                PathwayModification(
                    modification_type=ModificationType.INTENSITY_REDUCED,
                    description="Treatment intensity reduced — consider goals of care discussion",
                    reason=f"Severe frailty ({ctx.frailty_score.value}) may limit tolerance for aggressive interventions",
                    context_factors=["frailty", "goals_of_care"],
                )
            )
        return mods


@register_rule("recurrent_admissions")
class RecurrentAdmissions(PersonalisationRule):
    """Patients with ≥2 admissions in 12 months get enhanced monitoring."""

    def evaluate(self, ctx: PatientContext, pathway_id: str) -> list[PathwayModification]:
        count = ctx.recent_admission_count(months=12)
        if count < 2:
            return []
        return [
            PathwayModification(
                modification_type=ModificationType.INTENSITY_INCREASED,
                description="Enhanced monitoring and follow-up frequency due to recurrent admissions",
                reason=f"Patient has had {count} admissions in the past 12 months",
                context_factors=["recurrent_admissions", f"admission_count:{count}"],
                evidence_reference="NICE NG56 — Multimorbidity",
            )
        ]


@register_rule("language_barrier_adaptation")
class LanguageBarrierAdaptation(PersonalisationRule):
    """Add interpreter service if language barrier detected."""

    def evaluate(self, ctx: PatientContext, pathway_id: str) -> list[PathwayModification]:
        if not ctx.social_history.interpreter_needed and not ctx.social_history.language_barrier:
            return []
        return [
            PathwayModification(
                modification_type=ModificationType.ACTIVITY_ADDED,
                description="Interpreter service required for all clinical consultations",
                reason="Patient has a language barrier or interpreter need flagged",
                context_factors=["language_barrier", f"language:{ctx.demographics.language}"],
            )
        ]


@register_rule("transport_barrier_followup")
class TransportBarrierFollowUp(PersonalisationRule):
    """Adapt follow-up to community or telehealth if transport barriers exist."""

    def evaluate(self, ctx: PatientContext, pathway_id: str) -> list[PathwayModification]:
        if not ctx.social_history.transport_access or ctx.social_history.transport_access.lower() in ("good", "available", ""):
            return []
        return [
            PathwayModification(
                modification_type=ModificationType.FOLLOW_UP_ADAPTED,
                description="Follow-up adapted to telehealth or community visit due to transport barriers",
                reason=f"Transport access: {ctx.social_history.transport_access}",
                context_factors=["transport_barrier", "social_determinant"],
            )
        ]


# ── Heart failure specific ──────────────────────────────────────────

@register_rule("hf_ckd_renal_safe")
class HeartFailureCKDRenalSafe(PersonalisationRule):
    """HF + CKD: Use renal-safe diagnostics, adjust medications."""

    def applies_to_pathway(self, pathway_id: str) -> bool:
        return "heart" in pathway_id.lower() or "hf" in pathway_id.lower()

    def evaluate(self, ctx: PatientContext, pathway_id: str) -> list[PathwayModification]:
        if not self.applies_to_pathway(pathway_id):
            return []
        has_ckd = ctx.has_condition("ckd") or ctx.has_condition("chronic_kidney_disease") or any(
            "ckd" in c.code.lower() for c in ctx.conditions
        )
        egfr = ctx.observation_value("egfr")
        if not has_ckd and (egfr is None or egfr >= 60):
            return []

        mods = [
            PathwayModification(
                modification_type=ModificationType.SEQUENCE_CHANGED,
                node_id="action-initial-assessment",
                description="Medication review prioritised before diagnostics due to CKD comorbidity",
                reason=f"Patient has CKD (eGFR: {egfr}). Renal-safe approach required.",
                context_factors=["ckd", f"egfr:{egfr}"],
                evidence_reference="NICE NG106 — Heart failure, NICE CG182 — CKD",
            ),
            PathwayModification(
                modification_type=ModificationType.URGENCY_ELEVATED,
                node_id="action-specialist-referral",
                description="Expedited cardiology referral due to CKD-HF comorbidity",
                reason="CKD + heart failure combination requires specialist cardio-renal management",
                context_factors=["ckd", "heart_failure", "multimorbidity"],
                evidence_reference="NICE NG106",
            ),
        ]
        if egfr is not None and egfr < 30:
            mods.append(
                PathwayModification(
                    modification_type=ModificationType.CONTRAINDICATION_FLAGGED,
                    activity_id="hf-mra",
                    description="MRA contraindicated — eGFR < 30",
                    reason=f"eGFR {egfr} < 30 mL/min — MRA (spironolactone/eplerenone) contraindicated",
                    context_factors=["ckd", f"egfr:{egfr}", "contraindication"],
                    evidence_reference="NICE NG106, BNF",
                )
            )
        return mods


@register_rule("hf_polypharmacy_review")
class HeartFailurePolypharmacyReview(PersonalisationRule):
    """HF patients with polypharmacy get medication review first."""

    def applies_to_pathway(self, pathway_id: str) -> bool:
        return "heart" in pathway_id.lower()

    def evaluate(self, ctx: PatientContext, pathway_id: str) -> list[PathwayModification]:
        if not self.applies_to_pathway(pathway_id):
            return []
        if not ctx.is_polypharmacy(threshold=5):
            return []
        return [
            PathwayModification(
                modification_type=ModificationType.SEQUENCE_CHANGED,
                description="Medication review prioritised due to polypharmacy in heart failure patient",
                reason=f"Patient on {ctx.medication_count()} medications — polypharmacy review required before treatment changes",
                context_factors=["polypharmacy", "heart_failure"],
                evidence_reference="NICE NG56, NICE NG106",
            )
        ]


# ── COPD specific ────────────────────────────────────────────────────

@register_rule("copd_chf_comorbidity")
class COPDHeartFailureComorbidity(PersonalisationRule):
    """COPD + CHF: Cautious beta-agonist use, fluid management awareness."""

    def applies_to_pathway(self, pathway_id: str) -> bool:
        return "copd" in pathway_id.lower()

    def evaluate(self, ctx: PatientContext, pathway_id: str) -> list[PathwayModification]:
        if not self.applies_to_pathway(pathway_id):
            return []
        if not ctx.has_condition("heart_failure") and not ctx.has_condition("chf"):
            return []
        return [
            PathwayModification(
                modification_type=ModificationType.SAFETY_OVERRIDE,
                description="Cautious bronchodilator use — cardiac comorbidity present",
                reason="Patient has concurrent heart failure. High-dose beta-agonists may exacerbate cardiac symptoms.",
                context_factors=["heart_failure", "copd", "drug_interaction"],
                evidence_reference="NICE NG115, NICE NG106",
            ),
            PathwayModification(
                modification_type=ModificationType.URGENCY_ELEVATED,
                node_id="action-specialist-referral",
                description="Joint respiratory-cardiology referral recommended",
                reason="COPD-CHF overlap requires coordinated specialist management",
                context_factors=["multimorbidity", "copd", "heart_failure"],
            ),
        ]


@register_rule("copd_frequent_exacerbations")
class COPDFrequentExacerbations(PersonalisationRule):
    """Patients with ≥2 exacerbations/year need enhanced COPD management."""

    def applies_to_pathway(self, pathway_id: str) -> bool:
        return "copd" in pathway_id.lower()

    def evaluate(self, ctx: PatientContext, pathway_id: str) -> list[PathwayModification]:
        if not self.applies_to_pathway(pathway_id):
            return []
        admission_count = ctx.recent_admission_count(months=12)
        if admission_count < 2:
            return []
        return [
            PathwayModification(
                modification_type=ModificationType.INTENSITY_INCREASED,
                description="Enhanced COPD management due to frequent exacerbations",
                reason=f"{admission_count} admissions in past 12 months — frequent exacerbator phenotype",
                context_factors=["frequent_exacerbations", f"admission_count:{admission_count}"],
                evidence_reference="NICE NG115 — COPD",
            ),
            PathwayModification(
                modification_type=ModificationType.ACTIVITY_ADDED,
                description="Self-management plan and rescue pack provision",
                reason="Frequent exacerbators benefit from self-management plans per NICE NG115",
                context_factors=["frequent_exacerbations", "self_management"],
                evidence_reference="NICE NG115",
            ),
        ]


# ── Diabetes specific ───────────────────────────────────────────────

@register_rule("dm2_renal_impairment")
class DiabetesRenalImpairment(PersonalisationRule):
    """T2DM + CKD: Metformin contraindication, SGLT2i preference."""

    def applies_to_pathway(self, pathway_id: str) -> bool:
        return "diabetes" in pathway_id.lower()

    def evaluate(self, ctx: PatientContext, pathway_id: str) -> list[PathwayModification]:
        if not self.applies_to_pathway(pathway_id):
            return []
        egfr = ctx.observation_value("egfr")
        if egfr is None or egfr >= 30:
            return []
        return [
            PathwayModification(
                modification_type=ModificationType.CONTRAINDICATION_FLAGGED,
                activity_id="dm2-metformin",
                description="Metformin contraindicated — eGFR < 30",
                reason=f"eGFR {egfr} < 30 mL/min — metformin contraindicated due to lactic acidosis risk",
                context_factors=["ckd", f"egfr:{egfr}", "metformin_contraindication"],
                evidence_reference="NICE NG28 — Type 2 diabetes, BNF",
            ),
            PathwayModification(
                modification_type=ModificationType.ACTIVITY_ADDED,
                description="Specialist renal-diabetes referral recommended",
                reason="Severe renal impairment with diabetes requires specialist endocrine-renal management",
                context_factors=["ckd", "diabetes", "specialist_referral"],
                evidence_reference="NICE NG28",
            ),
        ]


@register_rule("dm2_foot_ulcer_mdl")
class DiabetesFootUlcerMDT(PersonalisationRule):
    """T2DM with active foot ulcer: MDT podiatry branch per NICE NG19."""

    def applies_to_pathway(self, pathway_id: str) -> bool:
        return "diabetes" in pathway_id.lower()

    def evaluate(self, ctx: PatientContext, pathway_id: str) -> list[PathwayModification]:
        if not self.applies_to_pathway(pathway_id):
            return []
        has_ulcer = ctx.has_condition("diabetic_foot_ulcer") or ctx.has_condition("foot_ulcer")
        if not has_ulcer:
            return []
        hba1c = ctx.observation_value("hba1c")
        mods = [
            PathwayModification(
                modification_type=ModificationType.ACTIVITY_ADDED,
                description="MDT foot care referral — active diabetic foot ulcer",
                reason="Active foot ulcer requires multidisciplinary foot team within 24 hours per NICE NG19",
                context_factors=["diabetic_foot_ulcer"],
                evidence_reference="NICE NG19 — Diabetic foot problems",
            ),
            PathwayModification(
                modification_type=ModificationType.URGENCY_ELEVATED,
                description="Urgent diabetes review due to active foot ulcer",
                reason="Foot ulcer indicates poor glycaemic control and vascular complications",
                context_factors=["diabetic_foot_ulcer", "urgency"],
                evidence_reference="NICE NG19",
            ),
        ]
        if hba1c is not None and hba1c > 75:
            mods.append(
                PathwayModification(
                    modification_type=ModificationType.INTENSITY_INCREASED,
                    description="Intensive glycaemic management — HbA1c very high with foot ulcer",
                    reason=f"HbA1c {hba1c} mmol/mol with active foot ulcer — aggressive treatment intensification needed",
                    context_factors=["hba1c_high", "foot_ulcer", f"hba1c:{hba1c}"],
                    evidence_reference="NICE NG28",
                )
            )
        return mods


# ── Sepsis specific ──────────────────────────────────────────────────

@register_rule("sepsis_immunocompromised")
class SepsisImmunocompromised(PersonalisationRule):
    """Immunocompromised patients need broader antimicrobial cover."""

    def applies_to_pathway(self, pathway_id: str) -> bool:
        return "sepsis" in pathway_id.lower()

    def evaluate(self, ctx: PatientContext, pathway_id: str) -> list[PathwayModification]:
        if not self.applies_to_pathway(pathway_id):
            return []
        immuno_conditions = {"immunocompromised", "hiv", "chemotherapy", "organ_transplant", "immunosuppression"}
        is_immuno = any(c.code.lower() in immuno_conditions for c in ctx.conditions)
        if not is_immuno:
            return []
        return [
            PathwayModification(
                modification_type=ModificationType.INTENSITY_INCREASED,
                description="Broader antimicrobial coverage for immunocompromised patient",
                reason="Immunocompromised status increases risk of atypical and opportunistic infections",
                context_factors=["immunocompromised", "sepsis"],
                evidence_reference="NICE NG51, Surviving Sepsis Campaign",
            ),
            PathwayModification(
                modification_type=ModificationType.URGENCY_ELEVATED,
                description="Lower threshold for red-flag escalation in immunocompromised patient",
                reason="Immunocompromised patients may deteriorate rapidly with attenuated inflammatory response",
                context_factors=["immunocompromised", "rapid_deterioration_risk"],
                evidence_reference="NICE NG51",
            ),
        ]


@register_rule("sepsis_penicillin_allergy")
class SepsisPenicillinAllergy(PersonalisationRule):
    """Penicillin allergy requires alternative antimicrobial regimen."""

    def applies_to_pathway(self, pathway_id: str) -> bool:
        return "sepsis" in pathway_id.lower()

    def evaluate(self, ctx: PatientContext, pathway_id: str) -> list[PathwayModification]:
        if not self.applies_to_pathway(pathway_id):
            return []
        if not ctx.has_allergy("penicillin"):
            return []
        return [
            PathwayModification(
                modification_type=ModificationType.CONTRAINDICATION_FLAGGED,
                activity_id="sepsis-antibiotics",
                description="Penicillin allergy — use alternative antimicrobial regimen",
                reason="Patient has documented penicillin allergy. Must use non-penicillin empirical antibiotics.",
                context_factors=["penicillin_allergy", "antimicrobial_selection"],
                evidence_reference="NICE NG51, local antimicrobial guidelines",
            ),
        ]


@register_rule("sepsis_hf_cautious_fluids")
class SepsisHeartFailureCautiousFluid(PersonalisationRule):
    """Sepsis + HF: Cautious fluid resuscitation to avoid overload."""

    def applies_to_pathway(self, pathway_id: str) -> bool:
        return "sepsis" in pathway_id.lower()

    def evaluate(self, ctx: PatientContext, pathway_id: str) -> list[PathwayModification]:
        if not self.applies_to_pathway(pathway_id):
            return []
        if not ctx.has_condition("heart_failure") and not ctx.has_condition("chf"):
            return []
        return [
            PathwayModification(
                modification_type=ModificationType.SAFETY_OVERRIDE,
                activity_id="sepsis-fluids",
                description="Cautious fluid resuscitation — heart failure comorbidity",
                reason="Patient has heart failure. Aggressive fluid boluses risk pulmonary oedema. Use smaller volumes with frequent reassessment.",
                context_factors=["heart_failure", "fluid_overload_risk"],
                evidence_reference="NICE NG51, NICE NG106",
            ),
        ]


# ── Maternal health specific ────────────────────────────────────────

@register_rule("anc_advanced_maternal_age")
class ANCAdvancedMaternalAge(PersonalisationRule):
    """Advanced maternal age (≥40): enhanced monitoring."""

    def applies_to_pathway(self, pathway_id: str) -> bool:
        return "maternal" in pathway_id.lower() or "anc" in pathway_id.lower()

    def evaluate(self, ctx: PatientContext, pathway_id: str) -> list[PathwayModification]:
        if not self.applies_to_pathway(pathway_id):
            return []
        age = ctx.age
        if age is None or age < 40:
            return []
        return [
            PathwayModification(
                modification_type=ModificationType.INTENSITY_INCREASED,
                description="Enhanced antenatal monitoring for advanced maternal age",
                reason=f"Maternal age {age} ≥ 40 — increased risk of chromosomal abnormalities, gestational diabetes, pre-eclampsia",
                context_factors=["advanced_maternal_age", f"age:{age}"],
                evidence_reference="WHO ANC recommendations, NICE NG201",
            ),
        ]


@register_rule("anc_pre_eclampsia_history")
class ANCPreEclampsiaHistory(PersonalisationRule):
    """History of pre-eclampsia: aspirin prophylaxis and enhanced BP monitoring."""

    def applies_to_pathway(self, pathway_id: str) -> bool:
        return "maternal" in pathway_id.lower() or "anc" in pathway_id.lower()

    def evaluate(self, ctx: PatientContext, pathway_id: str) -> list[PathwayModification]:
        if not self.applies_to_pathway(pathway_id):
            return []
        if not ctx.has_condition("pre_eclampsia"):
            return []
        return [
            PathwayModification(
                modification_type=ModificationType.ACTIVITY_ADDED,
                description="Low-dose aspirin prophylaxis from 12 weeks",
                reason="Previous pre-eclampsia — aspirin 75-150mg daily from 12 weeks reduces recurrence risk",
                context_factors=["pre_eclampsia_history"],
                evidence_reference="NICE NG133 — Hypertension in pregnancy",
            ),
            PathwayModification(
                modification_type=ModificationType.INTENSITY_INCREASED,
                description="Increased BP monitoring frequency",
                reason="Previous pre-eclampsia requires closer blood pressure surveillance",
                context_factors=["pre_eclampsia_history", "bp_monitoring"],
                evidence_reference="NICE NG133",
            ),
        ]
