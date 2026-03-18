"""Engine output models — personalised pathway and explainability."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ModificationType(str, enum.Enum):
    BRANCH_SELECTED = "branch_selected"
    ACTIVITY_EXCLUDED = "activity_excluded"
    ACTIVITY_ADDED = "activity_added"
    SEQUENCE_CHANGED = "sequence_changed"
    URGENCY_ELEVATED = "urgency_elevated"
    URGENCY_REDUCED = "urgency_reduced"
    INTENSITY_INCREASED = "intensity_increased"
    INTENSITY_REDUCED = "intensity_reduced"
    CONTRAINDICATION_FLAGGED = "contraindication_flagged"
    SAFETY_OVERRIDE = "safety_override"
    FOLLOW_UP_ADAPTED = "follow_up_adapted"


class PathwayModification(BaseModel):
    """A single modification made to the standard pathway."""

    modification_type: ModificationType
    node_id: str = ""
    activity_id: str = ""
    description: str
    reason: str = Field(..., description="Which patient context factor drove this modification")
    context_factors: list[str] = Field(default_factory=list)
    evidence_reference: str = ""


class PersonalisedActivity(BaseModel):
    """An activity in the personalised encounter journey."""

    activity_id: str
    name: str
    category: str
    description: str = ""
    urgency: str = "routine"
    sequence_order: int = 0
    is_original: bool = True
    is_excluded: bool = False
    exclusion_reason: str = ""
    modifications: list[PathwayModification] = Field(default_factory=list)
    required_agent_capability: str = ""


class PersonalisedNode(BaseModel):
    """A node in the personalised pathway."""

    node_id: str
    name: str
    activities: list[PersonalisedActivity] = Field(default_factory=list)
    is_skipped: bool = False
    skip_reason: str = ""


class ConfidenceLevel(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    REQUIRES_CLINICIAN_REVIEW = "requires_clinician_review"


class ExplainabilityReport(BaseModel):
    """Full explainability output for the personalisation decision."""

    pathway_id: str
    pathway_title: str
    patient_id: str
    modifications: list[PathwayModification] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH
    safety_warnings: list[str] = Field(default_factory=list)
    context_summary: dict[str, Any] = Field(default_factory=dict)
    reasoning_chain: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    clinician_override_recommended: bool = False
    override_reason: str = ""

    @property
    def modification_count(self) -> int:
        return len(self.modifications)


class PersonalisedPathway(BaseModel):
    """The complete personalised encounter journey for one patient."""

    pathway_id: str
    pathway_title: str
    source_pathway_version: str
    patient_id: str
    personalised_at: datetime = Field(default_factory=datetime.utcnow)
    nodes: list[PersonalisedNode] = Field(default_factory=list)
    explainability: ExplainabilityReport
    encounter_journey_summary: str = ""
    deviation_register: Any | None = Field(
        None,
        description="Explicit documentation of all deviations from the standard pathway.",
    )

    @property
    def total_activities(self) -> int:
        return sum(
            len([a for a in n.activities if not a.is_excluded])
            for n in self.nodes
            if not n.is_skipped
        )

    @property
    def has_deviations(self) -> bool:
        return self.deviation_register is not None and self.deviation_register.has_deviations
