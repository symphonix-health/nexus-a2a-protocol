"""Context assembler — builds a PatientContext from raw FHIR-style data.

In production this would call BulletTrain's ContextAssembler service
(GET /v1/context/{user_id}).  Here we provide a builder that can
construct a PatientContext from dictionaries, enabling both real
integration and synthetic test scenarios.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import (
    Allergy,
    AllergyCategory,
    AllergySeverity,
    CarePreference,
    Condition,
    ConsentStatus,
    Demographics,
    Encounter,
    FamilyHistoryItem,
    FrailtyScore,
    Gender,
    Immunization,
    Medication,
    Observation,
    PatientContext,
    SocialHistory,
    VitalSigns,
)


class ContextAssembler:
    """Assembles a PatientContext from a raw dictionary payload.

    The expected input mirrors the FHIR-aligned context JSON proposed
    in the integration reports.
    """

    def assemble(self, raw: dict[str, Any]) -> PatientContext:
        """Convert a raw context dict into a validated PatientContext."""
        return PatientContext(
            demographics=self._build_demographics(raw.get("demographics") or raw.get("patient", {})),
            conditions=self._build_conditions(raw.get("conditions", [])),
            medications=self._build_medications(raw.get("medications", [])),
            allergies=self._build_allergies(raw.get("allergies", [])),
            observations=self._build_observations(raw.get("observations", [])),
            vital_signs=self._build_vital_signs(raw.get("vital_signs", {})),
            immunizations=self._build_immunizations(raw.get("immunizations", [])),
            family_history=self._build_family_history(raw.get("family_history", raw.get("familyHistory", []))),
            social_history=self._build_social_history(raw.get("social_history", raw.get("socialHistory", {}))),
            care_preferences=self._build_care_preferences(raw.get("care_preferences", raw.get("carePlans", []))),
            encounters=self._build_encounters(raw.get("encounters", [])),
            chief_complaint=raw.get("chief_complaint", ""),
            frailty_score=self._parse_frailty(raw.get("frailty_score")),
            consent_status=self._parse_consent(raw.get("consent_status", "active")),
            last_updated=self._parse_datetime(raw.get("last_updated") or raw.get("lastUpdated")),
        )

    # ── private builders ─────────────────────────────────────────

    @staticmethod
    def _build_demographics(data: dict[str, Any]) -> Demographics:
        return Demographics(
            patient_id=data.get("patient_id", data.get("id", "unknown")),
            given_name=data.get("given_name", data.get("givenName", "")),
            family_name=data.get("family_name", data.get("familyName", "")),
            date_of_birth=data.get("date_of_birth", data.get("dateOfBirth")),
            age=data.get("age"),
            gender=Gender(data["gender"]) if data.get("gender") in Gender.__members__.values() else Gender.UNKNOWN,
            national_id=data.get("national_id", data.get("nationalID", "")),
            address=data.get("address", ""),
            telecom=data.get("telecom", ""),
            language=data.get("language", "en"),
        )

    @staticmethod
    def _build_conditions(items: list[dict[str, Any]]) -> list[Condition]:
        return [
            Condition(
                code=c.get("code", ""),
                display=c.get("display", c.get("name", "")),
                status=c.get("status", "active"),
                onset_date=c.get("onset_date", c.get("onsetDate")),
                snomed_code=c.get("snomed_code", ""),
            )
            for c in items
        ]

    @staticmethod
    def _build_medications(items: list[dict[str, Any]]) -> list[Medication]:
        return [
            Medication(
                code=m.get("code", m.get("name", "")),
                display=m.get("display", m.get("name", "")),
                dose=m.get("dose", ""),
                frequency=m.get("frequency", ""),
                route=m.get("route", ""),
                status=m.get("status", "active"),
                start_date=m.get("start_date"),
            )
            for m in items
        ]

    @staticmethod
    def _build_allergies(items: list[dict[str, Any]]) -> list[Allergy]:
        return [
            Allergy(
                substance=a.get("substance", a.get("name", "")),
                category=a.get("category", AllergyCategory.MEDICATION),
                reaction=a.get("reaction", ""),
                severity=a.get("severity", AllergySeverity.MODERATE),
            )
            for a in items
        ]

    @staticmethod
    def _build_observations(items: list[dict[str, Any]]) -> list[Observation]:
        return [
            Observation(
                code=o.get("code", ""),
                display=o.get("display", ""),
                value=o.get("value"),
                unit=o.get("unit", ""),
                reference_range=o.get("reference_range", o.get("referenceRange", "")),
                interpretation=o.get("interpretation", ""),
                date_recorded=ContextAssembler._parse_datetime(o.get("date_recorded") or o.get("dateRecorded")),
            )
            for o in items
        ]

    @staticmethod
    def _build_vital_signs(data: dict[str, Any]) -> VitalSigns:
        if not data:
            return VitalSigns()
        return VitalSigns(
            heart_rate=data.get("heart_rate"),
            systolic_bp=data.get("systolic_bp", data.get("blood_pressure", {}).get("systolic") if isinstance(data.get("blood_pressure"), dict) else None),
            diastolic_bp=data.get("diastolic_bp", data.get("blood_pressure", {}).get("diastolic") if isinstance(data.get("blood_pressure"), dict) else None),
            respiratory_rate=data.get("respiratory_rate"),
            temperature=data.get("temperature"),
            spo2=data.get("spo2"),
            consciousness=data.get("consciousness", "alert"),
            news2_score=data.get("news2_score"),
        )

    @staticmethod
    def _build_immunizations(items: list[dict[str, Any]]) -> list[Immunization]:
        return [
            Immunization(
                vaccine=i.get("vaccine", i.get("name", "")),
                date_given=i.get("date_given"),
                status=i.get("status", "completed"),
            )
            for i in items
        ]

    @staticmethod
    def _build_family_history(items: list[dict[str, Any]]) -> list[FamilyHistoryItem]:
        return [
            FamilyHistoryItem(
                condition=f.get("condition", ""),
                relationship=f.get("relationship", ""),
            )
            for f in items
        ]

    @staticmethod
    def _build_social_history(data: dict[str, Any]) -> SocialHistory:
        if not data:
            return SocialHistory()
        return SocialHistory(
            tobacco=data.get("tobacco", "unknown"),
            alcohol=data.get("alcohol", "unknown"),
            housing=data.get("housing", ""),
            employment=data.get("employment", ""),
            carer_support=data.get("carer_support", ""),
            transport_access=data.get("transport_access", ""),
            language_barrier=data.get("language_barrier", False),
            interpreter_needed=data.get("interpreter_needed", False),
        )

    @staticmethod
    def _build_care_preferences(items: list[dict[str, Any]]) -> list[CarePreference]:
        return [
            CarePreference(
                preference_type=cp.get("preference_type", cp.get("type", "")),
                value=cp.get("value", ""),
                description=cp.get("description", ""),
            )
            for cp in items
        ]

    @staticmethod
    def _build_encounters(items: list[dict[str, Any]]) -> list[Encounter]:
        return [
            Encounter(
                encounter_id=e.get("encounter_id", e.get("id", "")),
                encounter_type=e.get("encounter_type", e.get("type", "")),
                date=ContextAssembler._parse_datetime(e.get("date")),
                reason=e.get("reason", ""),
                outcome=e.get("outcome", ""),
                provider=e.get("provider", ""),
            )
            for e in items
        ]

    @staticmethod
    def _parse_frailty(val: Any) -> FrailtyScore | None:
        if val is None:
            return None
        try:
            return FrailtyScore(val)
        except ValueError:
            return None

    @staticmethod
    def _parse_consent(val: Any) -> ConsentStatus:
        try:
            return ConsentStatus(val)
        except (ValueError, KeyError):
            return ConsentStatus.UNKNOWN

    @staticmethod
    def _parse_datetime(val: Any) -> datetime | None:
        if val is None:
            return None
        if isinstance(val, datetime):
            return val
        try:
            return datetime.fromisoformat(str(val))
        except (ValueError, TypeError):
            return None
