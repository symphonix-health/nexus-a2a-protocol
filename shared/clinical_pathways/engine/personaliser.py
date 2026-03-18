"""Pathway Personaliser — the core decision engine.

Takes a national PathwayDefinition + PatientContext and produces a
PersonalisedPathway with full explainability.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Sequence

from ..context.models import ConsentStatus, PatientContext
from ..models import PathwayDefinition
from .audit import AuditLogger
from .models import (
    ConfidenceLevel,
    ExplainabilityReport,
    ModificationType,
    PathwayModification,
    PersonalisedActivity,
    PersonalisedNode,
    PersonalisedPathway,
)
from .deviation import build_deviation_register
from .rules import PersonalisationRule, get_all_rules
from .safety import SafetyGuardrails

logger = logging.getLogger(__name__)


class PathwayNotApplicableError(Exception):
    """Raised when the patient does not meet pathway entry criteria."""


class PathwayPersonaliser:
    """Applies patient context to a national pathway to produce
    an individualised encounter journey.
    """

    def __init__(
        self,
        *,
        audit_logger: AuditLogger | None = None,
        additional_rules: Sequence[tuple[str, PersonalisationRule]] | None = None,
    ) -> None:
        self._safety = SafetyGuardrails()
        self._audit = audit_logger or AuditLogger()
        self._rules = list(get_all_rules())
        if additional_rules:
            self._rules.extend(additional_rules)

    def personalise(
        self,
        pathway: PathwayDefinition,
        context: PatientContext,
        *,
        requesting_role: str = "",
        requesting_agent: str = "",
    ) -> PersonalisedPathway:
        """Personalise *pathway* for *context* and return the result."""
        pid = context.demographics.patient_id
        pseudo_pid = hashlib.sha256(pid.encode()).hexdigest()[:16]

        # 1. Collect all rule-based modifications
        rule_mods = self._apply_rules(pathway, context)

        # 2. Run safety guardrails
        safety_mods = self._safety.check_all(pathway, context)

        # 3. Merge and deduplicate modifications
        all_mods = self._merge_modifications(rule_mods, safety_mods)

        # 4. Determine confidence
        confidence = self._assess_confidence(all_mods, context)

        # 5. Build safety warnings list
        safety_warnings = [
            m.description
            for m in all_mods
            if m.modification_type in (ModificationType.SAFETY_OVERRIDE, ModificationType.CONTRAINDICATION_FLAGGED)
        ]

        # 6. Build context summary
        context_summary = self._build_context_summary(context)

        # 7. Build reasoning chain
        reasoning_chain = self._build_reasoning_chain(pathway, context, all_mods)

        # 8. Determine if clinician override is recommended
        override_recommended = (
            confidence in (ConfidenceLevel.LOW, ConfidenceLevel.REQUIRES_CLINICIAN_REVIEW)
            or len(safety_warnings) > 2
            or any(m.modification_type == ModificationType.SAFETY_OVERRIDE for m in all_mods)
        )

        # 9. Build explainability report
        explainability = ExplainabilityReport(
            pathway_id=pathway.pathway_id,
            pathway_title=pathway.title,
            patient_id=pseudo_pid,
            modifications=all_mods,
            confidence=confidence,
            safety_warnings=safety_warnings,
            context_summary=context_summary,
            reasoning_chain=reasoning_chain,
            evidence_references=pathway.evidence_references,
            clinician_override_recommended=override_recommended,
            override_reason="Multiple safety concerns require clinician review" if override_recommended else "",
        )

        # 10. Build personalised nodes
        personalised_nodes = self._build_personalised_nodes(pathway, all_mods)

        # 11. Generate encounter journey summary
        summary = self._generate_summary(pathway, context, all_mods)

        # 12. Build deviation register — explicit standard vs individualised documentation
        deviation_register = build_deviation_register(
            pathway_id=pathway.pathway_id,
            pathway_title=pathway.title,
            pathway_version=pathway.version,
            patient_id_pseudonymised=pseudo_pid,
            modifications=all_mods,
            confidence=confidence,
        )

        result = PersonalisedPathway(
            pathway_id=pathway.pathway_id,
            pathway_title=pathway.title,
            source_pathway_version=pathway.version,
            patient_id=pseudo_pid,
            personalised_at=datetime.utcnow(),
            nodes=personalised_nodes,
            explainability=explainability,
            encounter_journey_summary=summary,
            deviation_register=deviation_register,
        )

        # 13. Audit log
        self._audit.log_personalisation(
            result,
            requesting_role=requesting_role,
            requesting_agent=requesting_agent,
        )

        return result

    # ── private methods ──────────────────────────────────────────

    def _apply_rules(
        self,
        pathway: PathwayDefinition,
        ctx: PatientContext,
    ) -> list[PathwayModification]:
        mods: list[PathwayModification] = []
        for rule_name, rule in self._rules:
            if rule.applies_to_pathway(pathway.pathway_id):
                try:
                    result = rule.evaluate(ctx, pathway.pathway_id)
                    mods.extend(result)
                except Exception:
                    logger.warning("Rule '%s' failed", rule_name, exc_info=True)
        return mods

    @staticmethod
    def _merge_modifications(
        rule_mods: list[PathwayModification],
        safety_mods: list[PathwayModification],
    ) -> list[PathwayModification]:
        """Merge rule and safety modifications, deduplicating by description."""
        seen: set[str] = set()
        merged: list[PathwayModification] = []
        # Safety first (higher priority)
        for m in safety_mods + rule_mods:
            key = f"{m.modification_type}:{m.activity_id}:{m.description[:80]}"
            if key not in seen:
                seen.add(key)
                merged.append(m)
        return merged

    @staticmethod
    def _assess_confidence(
        mods: list[PathwayModification],
        ctx: PatientContext,
    ) -> ConfidenceLevel:
        safety_count = sum(
            1
            for m in mods
            if m.modification_type in (ModificationType.SAFETY_OVERRIDE, ModificationType.CONTRAINDICATION_FLAGGED)
        )
        if safety_count >= 3:
            return ConfidenceLevel.REQUIRES_CLINICIAN_REVIEW
        if safety_count >= 1:
            return ConfidenceLevel.MEDIUM
        if len(mods) > 5:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.HIGH

    @staticmethod
    def _build_context_summary(ctx: PatientContext) -> dict:
        return {
            "age": ctx.age,
            "gender": ctx.demographics.gender.value,
            "active_conditions": [c.code for c in ctx.conditions if c.status.value == "active"],
            "medication_count": ctx.medication_count(),
            "polypharmacy": ctx.is_polypharmacy(),
            "allergy_count": len(ctx.allergies),
            "frailty": ctx.frailty_score.value if ctx.frailty_score else None,
            "recent_admissions_12m": ctx.recent_admission_count(12),
            "language_barrier": ctx.social_history.language_barrier,
        }

    @staticmethod
    def _build_reasoning_chain(
        pathway: PathwayDefinition,
        ctx: PatientContext,
        mods: list[PathwayModification],
    ) -> list[str]:
        chain = [
            f"Patient assessed against pathway: {pathway.title} (v{pathway.version})",
            f"Source authority: {pathway.source_authority}",
            f"Patient age: {ctx.age}, gender: {ctx.demographics.gender.value}",
        ]
        if ctx.conditions:
            chain.append(f"Active conditions: {', '.join(c.code for c in ctx.conditions if c.status.value == 'active')}")
        if ctx.is_polypharmacy():
            chain.append(f"Polypharmacy detected: {ctx.medication_count()} active medications")
        if ctx.frailty_score:
            chain.append(f"Frailty score: {ctx.frailty_score.value}")
        for m in mods:
            chain.append(f"Modification: {m.description} — Reason: {m.reason}")
        return chain

    def _build_personalised_nodes(
        self,
        pathway: PathwayDefinition,
        mods: list[PathwayModification],
    ) -> list[PersonalisedNode]:
        """Convert pathway nodes to personalised nodes with modifications applied."""
        mod_by_node: dict[str, list[PathwayModification]] = {}
        mod_by_activity: dict[str, list[PathwayModification]] = {}
        for m in mods:
            if m.node_id:
                mod_by_node.setdefault(m.node_id, []).append(m)
            if m.activity_id:
                mod_by_activity.setdefault(m.activity_id, []).append(m)

        personalised_nodes = []
        order = 0
        for node in pathway.nodes:
            p_activities = []
            for act in node.activities:
                order += 1
                act_mods = mod_by_activity.get(act.activity_id, [])
                is_excluded = any(
                    m.modification_type == ModificationType.CONTRAINDICATION_FLAGGED
                    for m in act_mods
                )
                p_activities.append(
                    PersonalisedActivity(
                        activity_id=act.activity_id,
                        name=act.name,
                        category=act.category.value,
                        description=act.description,
                        urgency=act.urgency.value,
                        sequence_order=order,
                        is_original=True,
                        is_excluded=is_excluded,
                        exclusion_reason=act_mods[0].reason if is_excluded and act_mods else "",
                        modifications=act_mods,
                        required_agent_capability=act.required_agent_capability or "",
                    )
                )

            personalised_nodes.append(
                PersonalisedNode(
                    node_id=node.node_id,
                    name=node.name,
                    activities=p_activities,
                )
            )

        return personalised_nodes

    @staticmethod
    def _generate_summary(
        pathway: PathwayDefinition,
        ctx: PatientContext,
        mods: list[PathwayModification],
    ) -> str:
        parts = [f"Personalised {pathway.title} for patient (age {ctx.age}, {ctx.demographics.gender.value})."]
        if mods:
            parts.append(f"{len(mods)} modification(s) applied based on patient context:")
            for m in mods[:5]:
                parts.append(f"  - {m.description}")
            if len(mods) > 5:
                parts.append(f"  ... and {len(mods) - 5} more")
        else:
            parts.append("No personalisation modifications required — standard pathway applies.")
        return " ".join(parts)
