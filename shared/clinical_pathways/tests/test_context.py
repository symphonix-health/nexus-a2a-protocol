"""L5 Unit Tests — Patient context models, assembler, consent, redactor."""

import pytest
from clinical_pathways.context.assembler import ContextAssembler
from clinical_pathways.context.consent import ConsentChecker, ConsentDeniedError
from clinical_pathways.context.models import (
    ConsentStatus,
    Demographics,
    FrailtyScore,
    Gender,
    PatientContext,
)
from clinical_pathways.context.redactor import PHIRedactor

from .conftest import make_patient_context


class TestPatientContext:
    def test_has_condition(self):
        ctx = make_patient_context(conditions=[{"code": "heart_failure"}])
        assert ctx.has_condition("heart_failure") is True
        assert ctx.has_condition("copd") is False

    def test_has_allergy(self):
        ctx = make_patient_context(allergies=[{"substance": "penicillin"}])
        assert ctx.has_allergy("penicillin") is True
        assert ctx.has_allergy("aspirin") is False

    def test_medication_count(self):
        ctx = make_patient_context(medications=[
            {"code": "med1"}, {"code": "med2"}, {"code": "med3"},
        ])
        assert ctx.medication_count() == 3

    def test_polypharmacy_detection(self):
        meds = [{"code": f"med{i}"} for i in range(6)]
        ctx = make_patient_context(medications=meds)
        assert ctx.is_polypharmacy(threshold=5) is True
        assert ctx.is_polypharmacy(threshold=10) is False

    def test_observation_value(self):
        ctx = make_patient_context(observations=[
            {"code": "egfr", "value": 45.0, "unit": "mL/min"},
        ])
        assert ctx.observation_value("egfr") == 45.0
        assert ctx.observation_value("nonexistent") is None

    def test_age_property(self):
        ctx = make_patient_context(age=72)
        assert ctx.age == 72

    def test_active_medication_codes(self):
        ctx = make_patient_context(medications=[
            {"code": "ramipril", "status": "active"},
            {"code": "aspirin", "status": "stopped"},
        ])
        codes = ctx.active_medication_codes()
        assert "ramipril" in codes
        assert "aspirin" not in codes


class TestContextAssembler:
    def test_assemble_minimal(self, assembler):
        raw = {"demographics": {"patient_id": "P1", "age": 40, "gender": "male"}}
        ctx = assembler.assemble(raw)
        assert ctx.demographics.patient_id == "P1"
        assert ctx.age == 40

    def test_assemble_with_conditions(self, assembler):
        raw = {
            "demographics": {"patient_id": "P2", "age": 55},
            "conditions": [{"code": "copd", "display": "COPD"}],
        }
        ctx = assembler.assemble(raw)
        assert ctx.has_condition("copd")

    def test_assemble_with_vital_signs(self, assembler):
        raw = {
            "demographics": {"patient_id": "P3"},
            "vital_signs": {"heart_rate": 95, "systolic_bp": 130, "temperature": 37.5},
        }
        ctx = assembler.assemble(raw)
        assert ctx.vital_signs.heart_rate == 95
        assert ctx.vital_signs.systolic_bp == 130

    def test_assemble_with_allergies(self, assembler):
        raw = {
            "demographics": {"patient_id": "P4"},
            "allergies": [{"substance": "penicillin", "reaction": "rash"}],
        }
        ctx = assembler.assemble(raw)
        assert ctx.has_allergy("penicillin")

    def test_assemble_camelcase_keys(self, assembler):
        raw = {
            "patient": {"id": "P5", "givenName": "John", "familyName": "Doe"},
            "familyHistory": [{"condition": "diabetes", "relationship": "mother"}],
            "socialHistory": {"tobacco": "current"},
        }
        ctx = assembler.assemble(raw)
        assert ctx.demographics.patient_id == "P5"
        assert len(ctx.family_history) == 1
        assert ctx.social_history.tobacco == "current"


class TestConsentChecker:
    def test_active_consent_direct_care(self):
        checker = ConsentChecker()
        ctx = make_patient_context(consent_status="active")
        result = checker.check(ctx, purpose="direct_care")
        assert result is not None

    def test_denied_consent_raises(self):
        checker = ConsentChecker()
        ctx = make_patient_context(consent_status="denied")
        with pytest.raises(ConsentDeniedError):
            checker.check(ctx)

    def test_secondary_use_requires_active(self):
        checker = ConsentChecker()
        ctx = make_patient_context(consent_status="unknown")
        with pytest.raises(ConsentDeniedError):
            checker.check(ctx, purpose="research")

    def test_secondary_use_filters_sensitive(self):
        checker = ConsentChecker()
        ctx = make_patient_context(
            consent_status="active",
            conditions=[
                {"code": "heart_failure"},
                {"code": "mental_health"},
            ],
        )
        filtered = checker.check(ctx, purpose="research")
        assert not filtered.has_condition("mental_health")
        assert filtered.has_condition("heart_failure")


class TestPHIRedactor:
    def test_redact_names(self):
        redactor = PHIRedactor()
        ctx = make_patient_context(patient_id="REAL-ID")
        redacted = redactor.redact(ctx)
        assert redacted.demographics.given_name == "[REDACTED]"
        assert redacted.demographics.family_name == "[REDACTED]"
        assert redacted.demographics.national_id == "[REDACTED]"
        assert redacted.demographics.address == "[REDACTED]"
        assert redacted.demographics.patient_id != "REAL-ID"

    def test_redact_keeps_age(self):
        redactor = PHIRedactor()
        ctx = make_patient_context(age=55)
        redacted = redactor.redact(ctx, keep_age=True)
        assert redacted.age == 55

    def test_redact_removes_age_when_requested(self):
        redactor = PHIRedactor()
        ctx = make_patient_context(age=55)
        redacted = redactor.redact(ctx, keep_age=False)
        assert redacted.demographics.age is None

    def test_redact_preserves_clinical_data(self):
        redactor = PHIRedactor()
        ctx = make_patient_context(
            conditions=[{"code": "heart_failure"}],
            medications=[{"code": "ramipril"}],
        )
        redacted = redactor.redact(ctx)
        assert redacted.has_condition("heart_failure")
        assert "ramipril" in redacted.active_medication_codes()
