"""Shared fixtures for clinical-pathways tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the parent package importable as 'clinical_pathways'
_pkg_dir = Path(__file__).resolve().parent.parent
_ws_dir = _pkg_dir.parent
if str(_ws_dir) not in sys.path:
    sys.path.insert(0, str(_ws_dir))

# Register the hyphenated directory under an underscore alias
import importlib
import types

if "clinical_pathways" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "clinical_pathways",
        str(_pkg_dir / "__init__.py"),
        submodule_search_locations=[str(_pkg_dir)],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["clinical_pathways"] = mod
    spec.loader.exec_module(mod)

from clinical_pathways.context.assembler import ContextAssembler
from clinical_pathways.context.models import (
    Allergy,
    AllergyCategory,
    AllergySeverity,
    CarePreference,
    Condition,
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
from clinical_pathways.engine.audit import AuditLogger
from clinical_pathways.engine.personaliser import PathwayPersonaliser
from clinical_pathways.loader import load_pathways
from clinical_pathways.repository import PathwayRepository


@pytest.fixture
def pathway_repo() -> PathwayRepository:
    """Load all pathway definitions."""
    return load_pathways()


@pytest.fixture
def personaliser() -> PathwayPersonaliser:
    """Create a personaliser with default rules."""
    return PathwayPersonaliser(audit_logger=AuditLogger())


@pytest.fixture
def assembler() -> ContextAssembler:
    return ContextAssembler()


# ── Reusable patient context factories ───────────────────────────────

def make_patient_context(
    *,
    patient_id: str = "TEST-001",
    age: int = 55,
    gender: str = "male",
    conditions: list[dict] | None = None,
    medications: list[dict] | None = None,
    allergies: list[dict] | None = None,
    observations: list[dict] | None = None,
    vital_signs: dict | None = None,
    chief_complaint: str = "",
    frailty_score: str | None = None,
    social_history: dict | None = None,
    encounters: list[dict] | None = None,
    family_history: list[dict] | None = None,
    consent_status: str = "active",
) -> PatientContext:
    """Factory for creating test PatientContext objects."""
    return PatientContext(
        demographics=Demographics(
            patient_id=patient_id,
            given_name="Test",
            family_name="Patient",
            age=age,
            gender=Gender(gender) if gender in Gender.__members__.values() else Gender.UNKNOWN,
        ),
        conditions=[Condition(**c) for c in (conditions or [])],
        medications=[Medication(**m) for m in (medications or [])],
        allergies=[Allergy(**a) for a in (allergies or [])],
        observations=[Observation(**o) for o in (observations or [])],
        vital_signs=VitalSigns(**(vital_signs or {})),
        family_history=[FamilyHistoryItem(**f) for f in (family_history or [])],
        social_history=SocialHistory(**(social_history or {})),
        encounters=[Encounter(**e) for e in (encounters or [])],
        chief_complaint=chief_complaint,
        frailty_score=FrailtyScore(frailty_score) if frailty_score else None,
        consent_status=consent_status,
    )


@pytest.fixture
def healthy_patient() -> PatientContext:
    """Simple healthy patient with no comorbidities."""
    return make_patient_context(
        patient_id="HEALTHY-001",
        age=35,
        gender="female",
        chief_complaint="breathlessness",
    )


@pytest.fixture
def complex_hf_patient() -> PatientContext:
    """Complex heart failure patient — CKD, polypharmacy, frailty, recurrent admissions."""
    return make_patient_context(
        patient_id="COMPLEX-HF-001",
        age=72,
        gender="male",
        conditions=[
            {"code": "heart_failure", "display": "Chronic heart failure"},
            {"code": "ckd_stage_3", "display": "CKD Stage 3"},
            {"code": "hypertension", "display": "Hypertension"},
            {"code": "atrial_fibrillation", "display": "Atrial fibrillation"},
            {"code": "type_2_diabetes", "display": "Type 2 diabetes"},
        ],
        medications=[
            {"code": "ramipril", "display": "Ramipril 5mg", "dose": "5mg", "frequency": "daily"},
            {"code": "bisoprolol", "display": "Bisoprolol 5mg", "dose": "5mg", "frequency": "daily"},
            {"code": "spironolactone", "display": "Spironolactone 25mg", "dose": "25mg", "frequency": "daily"},
            {"code": "furosemide", "display": "Furosemide 40mg", "dose": "40mg", "frequency": "daily"},
            {"code": "metformin", "display": "Metformin 500mg", "dose": "500mg", "frequency": "twice daily"},
            {"code": "atorvastatin", "display": "Atorvastatin 80mg", "dose": "80mg", "frequency": "daily"},
            {"code": "warfarin", "display": "Warfarin 5mg", "dose": "5mg", "frequency": "daily"},
            {"code": "amlodipine", "display": "Amlodipine 5mg", "dose": "5mg", "frequency": "daily"},
            {"code": "omeprazole", "display": "Omeprazole 20mg", "dose": "20mg", "frequency": "daily"},
            {"code": "paracetamol", "display": "Paracetamol 1g PRN", "dose": "1g", "frequency": "prn"},
        ],
        allergies=[
            {"substance": "penicillin", "category": "medication", "reaction": "rash", "severity": "moderate"},
        ],
        observations=[
            {"code": "egfr", "value": 35.0, "unit": "mL/min/1.73m2"},
            {"code": "nt_pro_bnp", "value": 1800.0, "unit": "ng/L"},
            {"code": "potassium", "value": 5.1, "unit": "mmol/L"},
            {"code": "hba1c", "value": 58.0, "unit": "mmol/mol"},
        ],
        chief_complaint="breathlessness",
        frailty_score="moderate",
        social_history={"transport_access": "poor", "carer_support": "none"},
        encounters=[
            {"encounter_id": "E1", "encounter_type": "inpatient", "date": "2026-01-15T00:00:00", "reason": "HF exacerbation"},
            {"encounter_id": "E2", "encounter_type": "emergency", "date": "2025-11-20T00:00:00", "reason": "Breathlessness"},
            {"encounter_id": "E3", "encounter_type": "inpatient", "date": "2025-08-10T00:00:00", "reason": "HF exacerbation"},
        ],
    )


@pytest.fixture
def sepsis_patient() -> PatientContext:
    """Patient presenting with suspected sepsis."""
    return make_patient_context(
        patient_id="SEPSIS-001",
        age=68,
        gender="female",
        conditions=[
            {"code": "urinary_tract_infection", "display": "UTI"},
        ],
        medications=[
            {"code": "amlodipine", "display": "Amlodipine 5mg"},
        ],
        allergies=[
            {"substance": "penicillin", "category": "medication", "reaction": "anaphylaxis", "severity": "severe"},
        ],
        vital_signs={
            "heart_rate": 110,
            "systolic_bp": 85,
            "respiratory_rate": 24,
            "temperature": 38.9,
            "spo2": 93,
            "consciousness": "alert",
        },
        observations=[
            {"code": "lactate", "value": 3.5, "unit": "mmol/L"},
        ],
        chief_complaint="fever",
    )


@pytest.fixture
def diabetes_ckd_patient() -> PatientContext:
    """T2DM patient with renal impairment and foot ulcer."""
    return make_patient_context(
        patient_id="DM2-CKD-001",
        age=65,
        gender="male",
        conditions=[
            {"code": "type_2_diabetes", "display": "Type 2 diabetes mellitus"},
            {"code": "ckd_stage_4", "display": "CKD Stage 4"},
            {"code": "diabetic_foot_ulcer", "display": "Active diabetic foot ulcer"},
            {"code": "hypertension", "display": "Hypertension"},
        ],
        medications=[
            {"code": "metformin", "display": "Metformin 1g BD"},
            {"code": "gliclazide", "display": "Gliclazide 80mg"},
            {"code": "ramipril", "display": "Ramipril 10mg"},
            {"code": "amlodipine", "display": "Amlodipine 10mg"},
            {"code": "atorvastatin", "display": "Atorvastatin 80mg"},
        ],
        observations=[
            {"code": "egfr", "value": 22.0, "unit": "mL/min/1.73m2"},
            {"code": "hba1c", "value": 82.0, "unit": "mmol/mol"},
            {"code": "potassium", "value": 5.3, "unit": "mmol/L"},
        ],
        chief_complaint="foot ulcer review",
    )
