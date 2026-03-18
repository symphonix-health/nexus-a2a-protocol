"""Patient context models — FHIR-aligned Pydantic schemas.

These models represent the computable patient portrait consumed by the
Pathway Intelligence Engine.  Field names mirror FHIR R4/R5 resource
attributes but are kept as plain Pydantic to avoid heavyweight
FHIR-library dependencies.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────

class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNKNOWN = "unknown"


class ConditionStatus(str, enum.Enum):
    ACTIVE = "active"
    RECURRENCE = "recurrence"
    RELAPSE = "relapse"
    INACTIVE = "inactive"
    REMISSION = "remission"
    RESOLVED = "resolved"


class MedicationStatus(str, enum.Enum):
    ACTIVE = "active"
    ON_HOLD = "on-hold"
    STOPPED = "stopped"
    COMPLETED = "completed"


class AllergyCategory(str, enum.Enum):
    FOOD = "food"
    MEDICATION = "medication"
    ENVIRONMENT = "environment"
    BIOLOGIC = "biologic"


class AllergySeverity(str, enum.Enum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class ConsentStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DENIED = "denied"
    UNKNOWN = "unknown"


class FrailtyScore(str, enum.Enum):
    FIT = "fit"
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    VERY_SEVERE = "very_severe"
    TERMINALLY_ILL = "terminally_ill"


# ── Sub-models ───────────────────────────────────────────────────────

class Demographics(BaseModel):
    patient_id: str
    given_name: str = ""
    family_name: str = ""
    date_of_birth: date | None = None
    age: int | None = None
    gender: Gender = Gender.UNKNOWN
    national_id: str = ""
    address: str = ""
    telecom: str = ""
    language: str = "en"

    def compute_age(self) -> int | None:
        if self.date_of_birth is None:
            return self.age
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )


class Condition(BaseModel):
    code: str = Field(..., description="Coded condition, e.g. 'heart_failure', 'copd', 'ckd_stage_3'")
    display: str = ""
    status: ConditionStatus = ConditionStatus.ACTIVE
    onset_date: date | None = None
    snomed_code: str = ""


class Medication(BaseModel):
    code: str = Field(..., description="Drug code or canonical name")
    display: str = ""
    dose: str = ""
    frequency: str = ""
    route: str = ""
    status: MedicationStatus = MedicationStatus.ACTIVE
    start_date: date | None = None


class Allergy(BaseModel):
    substance: str
    category: AllergyCategory = AllergyCategory.MEDICATION
    reaction: str = ""
    severity: AllergySeverity = AllergySeverity.MODERATE


class Observation(BaseModel):
    code: str = Field(..., description="Observation code, e.g. 'heart_rate', 'egfr', 'hba1c'")
    display: str = ""
    value: float | None = None
    unit: str = ""
    reference_range: str = ""
    interpretation: str = ""
    date_recorded: datetime | None = None


class VitalSigns(BaseModel):
    heart_rate: float | None = None
    systolic_bp: float | None = None
    diastolic_bp: float | None = None
    respiratory_rate: float | None = None
    temperature: float | None = None
    spo2: float | None = None
    consciousness: str = "alert"
    news2_score: int | None = None


class Immunization(BaseModel):
    vaccine: str
    date_given: date | None = None
    status: str = "completed"


class FamilyHistoryItem(BaseModel):
    condition: str
    relationship: str = ""


class SocialHistory(BaseModel):
    tobacco: str = "unknown"
    alcohol: str = "unknown"
    housing: str = ""
    employment: str = ""
    carer_support: str = ""
    transport_access: str = ""
    language_barrier: bool = False
    interpreter_needed: bool = False


class CarePreference(BaseModel):
    preference_type: str = Field(..., description="E.g. 'advance_directive', 'dnr', 'preferred_language'")
    value: str = ""
    description: str = ""


class Encounter(BaseModel):
    encounter_id: str = ""
    encounter_type: str = ""
    date: datetime | None = None
    reason: str = ""
    outcome: str = ""
    provider: str = ""


# ── Main Patient Context Model ──────────────────────────────────────

class PatientContext(BaseModel):
    """The computable patient portrait.

    This is the single object consumed by the Pathway Intelligence Engine
    to personalise a national pathway for an individual patient.
    """

    demographics: Demographics
    conditions: list[Condition] = Field(default_factory=list)
    medications: list[Medication] = Field(default_factory=list)
    allergies: list[Allergy] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    vital_signs: VitalSigns = Field(default_factory=VitalSigns)
    immunizations: list[Immunization] = Field(default_factory=list)
    family_history: list[FamilyHistoryItem] = Field(default_factory=list)
    social_history: SocialHistory = Field(default_factory=SocialHistory)
    care_preferences: list[CarePreference] = Field(default_factory=list)
    encounters: list[Encounter] = Field(default_factory=list)
    chief_complaint: str = ""
    frailty_score: FrailtyScore | None = None
    consent_status: ConsentStatus = ConsentStatus.ACTIVE
    last_updated: datetime | None = None

    # ── convenience helpers ──────────────────────────────────────

    def has_condition(self, code: str) -> bool:
        return any(
            c.code.lower() == code.lower() and c.status == ConditionStatus.ACTIVE
            for c in self.conditions
        )

    def has_allergy(self, substance: str) -> bool:
        return any(a.substance.lower() == substance.lower() for a in self.allergies)

    def active_medication_codes(self) -> set[str]:
        return {m.code.lower() for m in self.medications if m.status == MedicationStatus.ACTIVE}

    def medication_count(self) -> int:
        return len([m for m in self.medications if m.status == MedicationStatus.ACTIVE])

    def is_polypharmacy(self, threshold: int = 5) -> bool:
        return self.medication_count() >= threshold

    def latest_observation(self, code: str) -> Observation | None:
        matches = [o for o in self.observations if o.code.lower() == code.lower()]
        if not matches:
            return None
        dated = [o for o in matches if o.date_recorded]
        if dated:
            return max(dated, key=lambda o: o.date_recorded)  # type: ignore[arg-type]
        return matches[-1]

    def observation_value(self, code: str) -> float | None:
        obs = self.latest_observation(code)
        return obs.value if obs else None

    def recent_admission_count(self, months: int = 12) -> int:
        if not self.encounters:
            return 0
        cutoff = datetime.now().replace(
            year=datetime.now().year if datetime.now().month > months else datetime.now().year - 1,
        )
        return len([
            e for e in self.encounters
            if e.encounter_type in ("inpatient", "emergency")
            and e.date is not None
            and e.date >= cutoff
        ])

    @property
    def age(self) -> int | None:
        return self.demographics.compute_age() or self.demographics.age
