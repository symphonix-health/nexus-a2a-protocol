"""Layer 1 — Pathway definition models.

Structured representations of national clinical pathways, modelled
after FHIR PlanDefinition / ActivityDefinition but kept as plain
Pydantic so the package has no heavyweight FHIR dependency.

Clinical pathways are regulated knowledge assets issued by authoritative
bodies (WHO, NICE, NHS England, etc.).  The governance metadata tracks
the full provenance chain from source guideline through local adoption,
enabling automated currency checks and audit-ready traceability.
"""

from __future__ import annotations

import enum
from datetime import date
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────

class PathwayStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"
    SUPERSEDED = "superseded"


class AuthorityLevel(str, enum.Enum):
    """Hierarchy of issuing authorities — higher levels take precedence."""
    INTERNATIONAL = "international"   # WHO, ICM
    NATIONAL = "national"             # NICE, NHS England, CDC, TGA
    REGIONAL = "regional"             # ICS, Health Board
    LOCAL = "local"                   # Trust, Practice


class NodeType(str, enum.Enum):
    ENTRY = "entry"
    DECISION = "decision"
    ACTION = "action"
    EXIT = "exit"


class ActivityCategory(str, enum.Enum):
    ASSESSMENT = "assessment"
    DIAGNOSTIC = "diagnostic"
    TREATMENT = "treatment"
    REFERRAL = "referral"
    MONITORING = "monitoring"
    COUNSELLING = "counselling"
    DISCHARGE = "discharge"
    REVIEW = "review"


class UrgencyLevel(str, enum.Enum):
    ROUTINE = "routine"
    URGENT = "urgent"
    EMERGENT = "emergent"


class ComparisonOperator(str, enum.Enum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GE = "ge"
    LT = "lt"
    LE = "le"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    EXISTS = "exists"


# ── Governance & Provenance ───────────────────────────────────────────

class GuidelineSource(BaseModel):
    """Authoritative source document that this pathway is derived from.

    Each pathway may reference multiple sources at different authority
    levels — e.g. a WHO recommendation adopted into a NICE guideline
    and then localised by a trust.
    """

    authority: str = Field(
        ...,
        description="Issuing body, e.g. 'WHO', 'NICE', 'NHS England', 'CDC'.",
    )
    authority_level: AuthorityLevel = Field(
        ...,
        description="Position in the governance hierarchy.",
    )
    guideline_id: str = Field(
        ...,
        description="Canonical identifier, e.g. 'NG106', 'NG51', 'WHO-ANC-2016'.",
    )
    title: str = Field(
        ...,
        description="Full title of the source guideline.",
    )
    url: str = Field(
        "",
        description="Canonical URL for the guideline.",
    )
    version: str = Field(
        "",
        description="Source guideline version or edition.",
    )
    publication_date: date | None = Field(
        None,
        description="Date the source guideline was published.",
    )
    last_updated: date | None = Field(
        None,
        description="Date the source guideline was last revised/updated by the authority.",
    )
    next_review_date: date | None = Field(
        None,
        description="Scheduled review date published by the authority.",
    )
    superseded_by: str | None = Field(
        None,
        description="Guideline ID of the replacement, if this source has been superseded.",
    )


class PathwayRevision(BaseModel):
    """An entry in the pathway's change history.

    Records who changed what, when, and why — essential for
    clinical governance audit trails.
    """

    revision_version: str = Field(
        ...,
        description="Version after this revision, e.g. '2.1'.",
    )
    revision_date: date = Field(
        ...,
        description="Date of the revision.",
    )
    author: str = Field(
        ...,
        description="Person or role who authored the revision.",
    )
    reason: str = Field(
        ...,
        description="Why the revision was made — guideline update, clinical safety finding, local adaptation, etc.",
    )
    source_update: str = Field(
        "",
        description="Reference to the upstream guideline change that triggered this revision.",
    )
    changes: list[str] = Field(
        default_factory=list,
        description="Summary of each discrete change made.",
    )
    approved_by: str = Field(
        "",
        description="Clinical governance approver.",
    )
    approval_date: date | None = Field(
        None,
        description="Date of clinical governance approval.",
    )


class GovernanceMetadata(BaseModel):
    """Full governance envelope wrapping every clinical pathway.

    Tracks the provenance chain from international standards through
    national guidelines to local adoption, including review schedules,
    revision history, and currency status.
    """

    sources: list[GuidelineSource] = Field(
        default_factory=list,
        description="All authoritative source documents, ordered by authority level (highest first).",
    )
    adopted_date: date | None = Field(
        None,
        description="Date this pathway was adopted into BulletTrain.",
    )
    adopted_by: str = Field(
        "",
        description="Clinical lead or governance board who approved adoption.",
    )
    last_reviewed_date: date | None = Field(
        None,
        description="Date of the most recent clinical review of this pathway asset.",
    )
    next_review_date: date | None = Field(
        None,
        description="Date by which this pathway must be reviewed for currency.",
    )
    review_frequency_months: int = Field(
        12,
        description="How often (in months) this pathway should be reviewed.",
    )
    revision_history: list[PathwayRevision] = Field(
        default_factory=list,
        description="Complete change log, newest first.",
    )
    clinical_owner: str = Field(
        "",
        description="Named clinical lead responsible for keeping this pathway current.",
    )
    governance_committee: str = Field(
        "",
        description="Committee or board with oversight, e.g. 'Clinical Effectiveness Committee'.",
    )
    local_adaptations: list[str] = Field(
        default_factory=list,
        description="Documented deviations from the source guideline, with rationale.",
    )

    # ── helpers ───────────────────────────────────────────────────

    def is_due_for_review(self, as_of: date | None = None) -> bool:
        """True if the pathway is past its scheduled review date."""
        if self.next_review_date is None:
            return False
        check_date = as_of or date.today()
        return check_date >= self.next_review_date

    def has_superseded_source(self) -> bool:
        """True if any source guideline has been marked as superseded."""
        return any(s.superseded_by is not None for s in self.sources)

    def highest_authority(self) -> AuthorityLevel | None:
        """Return the highest authority level among sources."""
        level_order = [
            AuthorityLevel.INTERNATIONAL,
            AuthorityLevel.NATIONAL,
            AuthorityLevel.REGIONAL,
            AuthorityLevel.LOCAL,
        ]
        for level in level_order:
            if any(s.authority_level == level for s in self.sources):
                return level
        return None


# ── Criterion ────────────────────────────────────────────────────────

class Criterion(BaseModel):
    """A single testable condition used in entry criteria or decision nodes."""

    field: str = Field(
        ...,
        description="Dot-path into PatientContext, e.g. 'demographics.age' or 'conditions[].code'.",
    )
    operator: ComparisonOperator
    value: Any = Field(
        None,
        description="Comparand.  Ignored for 'exists' operator.",
    )
    description: str = ""


class CriteriaGroup(BaseModel):
    """A conjunction (AND) of criteria.  Multiple groups are disjunctive (OR)."""

    criteria: list[Criterion] = Field(default_factory=list)
    description: str = ""


# ── Activity ─────────────────────────────────────────────────────────

class Activity(BaseModel):
    """A single step / action within a pathway."""

    activity_id: str
    name: str
    category: ActivityCategory
    description: str = ""
    required_agent_capability: str | None = Field(
        None,
        description="Capability tag used to discover an agent in GHARRA.",
    )
    contraindications: list[Criterion] = Field(default_factory=list)
    urgency: UrgencyLevel = UrgencyLevel.ROUTINE
    estimated_duration_minutes: int | None = None
    fhir_resource_type: str | None = Field(
        None,
        description="E.g. 'ServiceRequest', 'MedicationRequest', 'Encounter'.",
    )


# ── Decision Node ────────────────────────────────────────────────────

class DecisionBranch(BaseModel):
    """One branch from a decision node, taken when criteria match."""

    branch_id: str
    criteria: list[CriteriaGroup] = Field(default_factory=list)
    target_node_id: str
    description: str = ""


class PathwayNode(BaseModel):
    """A node in the pathway graph."""

    node_id: str
    node_type: NodeType
    name: str
    description: str = ""
    activities: list[Activity] = Field(default_factory=list)
    branches: list[DecisionBranch] = Field(
        default_factory=list,
        description="Only meaningful for DECISION nodes.",
    )
    default_next: str | None = Field(
        None,
        description="Fallback target when no branch matches (decision nodes) "
        "or the single next node (action nodes).",
    )


# ── Pathway Definition ───────────────────────────────────────────────

class PathwayDefinition(BaseModel):
    """A complete nationally approved clinical pathway.

    Analogous to FHIR PlanDefinition but stored as a lightweight
    JSON graph so it can be loaded, versioned, and interpreted
    without a full FHIR server.
    """

    pathway_id: str = Field(..., description="Globally unique identifier, e.g. 'nice-ng106-heart-failure'.")
    title: str
    version: str
    status: PathwayStatus = PathwayStatus.ACTIVE
    source_authority: str = Field(..., description="E.g. 'NICE', 'NHS England', 'WHO'.")
    guideline_reference: str = Field("", description="URL or document reference to the source guideline.")
    country: str = Field("GB", description="ISO 3166-1 alpha-2 country code.")
    publication_date: date | None = None
    description: str = ""

    # ── Governance ────────────────────────────────────────────────
    governance: GovernanceMetadata = Field(
        default_factory=GovernanceMetadata,
        description="Full provenance, review schedule, and revision history.",
    )

    entry_criteria: list[CriteriaGroup] = Field(
        default_factory=list,
        description="Criteria that must be met for the pathway to apply.",
    )
    nodes: list[PathwayNode] = Field(
        default_factory=list,
        description="All nodes in the pathway graph.",
    )
    evidence_references: list[str] = Field(
        default_factory=list,
        description="Citations or URLs backing the pathway.",
    )

    # ── helpers ───────────────────────────────────────────────────

    def get_node(self, node_id: str) -> PathwayNode | None:
        return next((n for n in self.nodes if n.node_id == node_id), None)

    def entry_node(self) -> PathwayNode | None:
        return next((n for n in self.nodes if n.node_type == NodeType.ENTRY), None)

    def exit_nodes(self) -> list[PathwayNode]:
        return [n for n in self.nodes if n.node_type == NodeType.EXIT]

    @property
    def node_index(self) -> dict[str, PathwayNode]:
        return {n.node_id: n for n in self.nodes}

    def is_current(self, as_of: date | None = None) -> bool:
        """True if the pathway is active, not superseded, and not overdue for review."""
        if self.status not in (PathwayStatus.ACTIVE,):
            return False
        if self.governance.has_superseded_source():
            return False
        if self.governance.is_due_for_review(as_of):
            return False
        return True

    def needs_attention(self, as_of: date | None = None) -> list[str]:
        """Return a list of governance concerns that need clinical attention."""
        concerns: list[str] = []
        if self.status == PathwayStatus.SUPERSEDED:
            concerns.append(f"Pathway has been superseded — check for replacement.")
        if self.governance.has_superseded_source():
            superseded = [s for s in self.governance.sources if s.superseded_by]
            for s in superseded:
                concerns.append(
                    f"Source '{s.guideline_id}' from {s.authority} has been "
                    f"superseded by '{s.superseded_by}' — pathway must be updated."
                )
        if self.governance.is_due_for_review(as_of):
            concerns.append(
                f"Review overdue — was due {self.governance.next_review_date}."
            )
        if not self.governance.sources:
            concerns.append("No authoritative sources documented — provenance gap.")
        if not self.governance.clinical_owner:
            concerns.append("No clinical owner assigned.")
        return concerns
