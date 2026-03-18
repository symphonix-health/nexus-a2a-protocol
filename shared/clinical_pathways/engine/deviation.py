"""Deviation Register — documents every change from the standard clinical pathway.

When an individualised clinical pathway differs from the nationally approved
standard, the deviation must be explicitly documented with:
  - What the standard pathway specifies
  - What the individualised pathway does instead
  - Why (which patient context factors drove the change)
  - Evidence (guideline reference supporting the deviation)
  - Whether clinical sign-off is required

This is a regulatory requirement for clinical decision support systems and
supports CQC inspection, clinical negligence defence, and audit readiness.
"""

from __future__ import annotations

import enum
from datetime import datetime
from pydantic import BaseModel, Field

from .models import ConfidenceLevel, ModificationType, PathwayModification


class DeviationSeverity(str, enum.Enum):
    """How significant is the deviation from the standard pathway."""

    MINOR = "minor"           # Sequence change, follow-up timing
    MODERATE = "moderate"     # Activity added/excluded, intensity change
    MAJOR = "major"           # Contraindication, safety override
    CRITICAL = "critical"     # Multiple safety overrides, requires clinician


class DeviationEntry(BaseModel):
    """A single documented deviation from the standard clinical pathway.

    Provides explicit before/after comparison showing what the national
    guideline specifies vs what the individualised pathway does.
    """

    deviation_id: str = Field(
        ...,
        description="Unique identifier, e.g. 'DEV-001'.",
    )
    use_case_id: str = Field(
        "",
        description="Which use case this deviation relates to, e.g. 'UC-02'.",
    )
    modification_type: ModificationType = Field(
        ...,
        description="Category of modification from the ModificationType enum.",
    )
    severity: DeviationSeverity = Field(
        ...,
        description="How significant is this deviation.",
    )

    # ── Standard vs Individualised ──────────────────────────────
    standard_pathway_step: str = Field(
        ...,
        description="What the national guideline / standard pathway specifies.",
    )
    individualised_step: str = Field(
        ...,
        description="What the individualised pathway does instead for this patient.",
    )
    node_id: str = Field(
        "",
        description="Pathway node where the deviation occurs.",
    )
    activity_id: str = Field(
        "",
        description="Specific activity affected.",
    )

    # ── Justification ───────────────────────────────────────────
    reason: str = Field(
        ...,
        description="Clinical reason for the deviation.",
    )
    context_factors: list[str] = Field(
        default_factory=list,
        description="Patient context factors that drove this deviation.",
    )
    evidence_reference: str = Field(
        "",
        description="NICE guideline, BNF, or other evidence reference.",
    )

    # ── Clinical governance ──────────────────────────────────────
    requires_clinician_signoff: bool = Field(
        False,
        description="Whether this deviation requires explicit clinician approval.",
    )
    clinician_signoff: str = Field(
        "",
        description="Name/role of clinician who approved the deviation.",
    )
    signoff_date: datetime | None = Field(
        None,
        description="Date/time of clinician sign-off.",
    )


class DeviationRegister(BaseModel):
    """Complete register of all deviations from the standard pathway
    for a single personalisation event.

    This is the auditable artefact that documents exactly what changed
    from the nationally approved pathway and why.
    """

    register_id: str = Field(
        ...,
        description="Unique register identifier.",
    )
    pathway_id: str = Field(
        ...,
        description="The standard pathway being deviated from.",
    )
    pathway_title: str = Field(
        "",
        description="Human-readable title of the standard pathway.",
    )
    pathway_version: str = Field(
        "",
        description="Version of the standard pathway.",
    )
    patient_id_pseudonymised: str = Field(
        ...,
        description="SHA-256 pseudonymised patient ID.",
    )
    personalised_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the personalisation was performed.",
    )

    # ── Deviations ───────────────────────────────────────────────
    deviations: list[DeviationEntry] = Field(
        default_factory=list,
        description="All documented deviations from the standard pathway.",
    )

    # ── Summary ──────────────────────────────────────────────────
    total_deviations: int = Field(
        0,
        description="Total number of deviations.",
    )
    deviation_severity_summary: dict[str, int] = Field(
        default_factory=dict,
        description="Count of deviations by severity level.",
    )
    requires_any_clinician_signoff: bool = Field(
        False,
        description="True if any deviation requires clinician approval.",
    )
    overall_confidence: ConfidenceLevel = Field(
        ConfidenceLevel.HIGH,
        description="Overall confidence in the personalised pathway.",
    )

    @property
    def has_deviations(self) -> bool:
        return len(self.deviations) > 0

    @property
    def critical_deviations(self) -> list[DeviationEntry]:
        return [d for d in self.deviations if d.severity == DeviationSeverity.CRITICAL]

    @property
    def major_deviations(self) -> list[DeviationEntry]:
        return [d for d in self.deviations if d.severity == DeviationSeverity.MAJOR]


# ── Builder ──────────────────────────────────────────────────────────

_SEVERITY_MAP: dict[ModificationType, DeviationSeverity] = {
    ModificationType.BRANCH_SELECTED: DeviationSeverity.MINOR,
    ModificationType.SEQUENCE_CHANGED: DeviationSeverity.MINOR,
    ModificationType.FOLLOW_UP_ADAPTED: DeviationSeverity.MINOR,
    ModificationType.ACTIVITY_ADDED: DeviationSeverity.MODERATE,
    ModificationType.ACTIVITY_EXCLUDED: DeviationSeverity.MODERATE,
    ModificationType.INTENSITY_INCREASED: DeviationSeverity.MODERATE,
    ModificationType.INTENSITY_REDUCED: DeviationSeverity.MODERATE,
    ModificationType.URGENCY_ELEVATED: DeviationSeverity.MODERATE,
    ModificationType.URGENCY_REDUCED: DeviationSeverity.MODERATE,
    ModificationType.CONTRAINDICATION_FLAGGED: DeviationSeverity.MAJOR,
    ModificationType.SAFETY_OVERRIDE: DeviationSeverity.CRITICAL,
}

_STANDARD_STEP_MAP: dict[ModificationType, str] = {
    ModificationType.BRANCH_SELECTED: "Standard pathway branch selection based on guidelines",
    ModificationType.SEQUENCE_CHANGED: "Standard activity sequence as defined in the pathway",
    ModificationType.FOLLOW_UP_ADAPTED: "Standard follow-up schedule (outpatient clinic attendance)",
    ModificationType.ACTIVITY_ADDED: "No additional activities beyond standard pathway",
    ModificationType.ACTIVITY_EXCLUDED: "Activity included as standard in the pathway",
    ModificationType.INTENSITY_INCREASED: "Standard treatment intensity as per guideline",
    ModificationType.INTENSITY_REDUCED: "Standard treatment intensity as per guideline",
    ModificationType.URGENCY_ELEVATED: "Routine urgency level as per pathway definition",
    ModificationType.URGENCY_REDUCED: "Standard urgency level as per pathway definition",
    ModificationType.CONTRAINDICATION_FLAGGED: "Medication/activity included in standard pathway",
    ModificationType.SAFETY_OVERRIDE: "Standard treatment approach without safety override",
}


def build_deviation_register(
    *,
    pathway_id: str,
    pathway_title: str,
    pathway_version: str,
    patient_id_pseudonymised: str,
    modifications: list[PathwayModification],
    confidence: ConfidenceLevel,
    register_id: str = "",
) -> DeviationRegister:
    """Build a DeviationRegister from a list of PathwayModifications.

    Converts each modification into a documented deviation entry showing
    the standard pathway step vs the individualised step.
    """
    deviations: list[DeviationEntry] = []

    for i, mod in enumerate(modifications, 1):
        severity = _SEVERITY_MAP.get(mod.modification_type, DeviationSeverity.MODERATE)
        standard_step = _STANDARD_STEP_MAP.get(
            mod.modification_type,
            "Standard pathway step as per guideline",
        )
        requires_signoff = severity in (DeviationSeverity.MAJOR, DeviationSeverity.CRITICAL)

        deviations.append(
            DeviationEntry(
                deviation_id=f"DEV-{i:03d}",
                modification_type=mod.modification_type,
                severity=severity,
                standard_pathway_step=standard_step,
                individualised_step=mod.description,
                node_id=mod.node_id,
                activity_id=mod.activity_id,
                reason=mod.reason,
                context_factors=mod.context_factors,
                evidence_reference=mod.evidence_reference,
                requires_clinician_signoff=requires_signoff,
            )
        )

    severity_summary: dict[str, int] = {}
    for d in deviations:
        severity_summary[d.severity.value] = severity_summary.get(d.severity.value, 0) + 1

    return DeviationRegister(
        register_id=register_id or f"DEVREG-{pathway_id}-{patient_id_pseudonymised[:8]}",
        pathway_id=pathway_id,
        pathway_title=pathway_title,
        pathway_version=pathway_version,
        patient_id_pseudonymised=patient_id_pseudonymised,
        deviations=deviations,
        total_deviations=len(deviations),
        deviation_severity_summary=severity_summary,
        requires_any_clinician_signoff=any(d.requires_clinician_signoff for d in deviations),
        overall_confidence=confidence,
    )
