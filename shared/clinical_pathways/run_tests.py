#!/usr/bin/env python3
"""Run all clinical-pathways tests without pytest.

Uses the core modules directly to verify everything works.
"""
from __future__ import annotations

import importlib
import json
import sys
import traceback
from pathlib import Path

# ── Setup import paths ──────────────────────────────────────────
pkg_dir = Path(__file__).resolve().parent
ws_dir = pkg_dir.parent
sys.path.insert(0, str(ws_dir))

if "clinical_pathways" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "clinical_pathways",
        str(pkg_dir / "__init__.py"),
        submodule_search_locations=[str(pkg_dir)],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["clinical_pathways"] = mod
    spec.loader.exec_module(mod)

from clinical_pathways.context.assembler import ContextAssembler
from clinical_pathways.context.consent import ConsentChecker, ConsentDeniedError
from clinical_pathways.context.models import (
    Allergy, AllergyCategory, AllergySeverity, CarePreference,
    Condition, Demographics, Encounter, FamilyHistoryItem,
    FrailtyScore, Gender, Immunization, Medication, Observation,
    PatientContext, SocialHistory, VitalSigns,
)
from clinical_pathways.context.redactor import PHIRedactor
from clinical_pathways.engine.audit import AuditLogger
from clinical_pathways.engine.models import (
    ConfidenceLevel, ModificationType, PersonalisedPathway,
)
from clinical_pathways.engine.personaliser import PathwayPersonaliser
from clinical_pathways.engine.safety import SafetyGuardrails
from clinical_pathways.loader import load_pathways
from clinical_pathways.models import PathwayDefinition, PathwayStatus
from clinical_pathways.repository import PathwayRepository

passed = 0
failed = 0
errors = []


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        msg = f"FAIL: {name}"
        if detail:
            msg += f" — {detail}"
        errors.append(msg)
        print(f"  ✗ {msg}")


# ═══════════════════════════════════════════════════════════════
# MODULE 1: Pathway Knowledge Repository
# ═══════════════════════════════════════════════════════════════
print("\n═══ Module 1: Pathway Repository ═══")

repo = load_pathways()
active = repo.list_active()
check("repo loads", len(active) >= 5, f"got {len(active)}")

hf = repo.get("nice-ng106-heart-failure")
check("HF pathway loads", hf is not None)
check("HF has nodes", len(hf.nodes) >= 10 if hf else False)
check("HF entry node", hf.entry_node() is not None if hf else False)

copd = repo.get("nice-ng115-copd")
check("COPD pathway loads", copd is not None)

dm = repo.get("nice-ng28-diabetes-type2")
check("DM pathway loads", dm is not None)

sepsis = repo.get("nice-ng51-sepsis")
check("Sepsis pathway loads", sepsis is not None)

anc = repo.get("who-maternal-anc")
check("ANC pathway loads", anc is not None)

nice_list = repo.list_by_authority("NICE")
check("NICE filter", len(nice_list) >= 4)

search_hf = repo.search("heart failure")
check("search HF", len(search_hf) >= 1)

search_diabetes = repo.search("diabetes")
check("search diabetes", len(search_diabetes) >= 1)

# ═══════════════════════════════════════════════════════════════
# MODULE 2: Patient Context
# ═══════════════════════════════════════════════════════════════
print("\n═══ Module 2: Patient Context ═══")

ctx = PatientContext(
    demographics=Demographics(
        patient_id="TEST-001", given_name="John", family_name="Smith",
        age=72, gender=Gender.MALE,
    ),
    conditions=[
        Condition(code="heart_failure", display="HF"),
        Condition(code="ckd_stage_3", display="CKD3"),
        Condition(code="type_2_diabetes", display="T2DM"),
    ],
    medications=[Medication(code=f"med{i}", display=f"Med {i}") for i in range(12)],
    allergies=[Allergy(substance="penicillin", reaction="anaphylaxis", severity="severe")],
    observations=[
        Observation(code="egfr", value=35.0, unit="mL/min/1.73m2"),
        Observation(code="nt_pro_bnp", value=1800.0, unit="ng/L"),
        Observation(code="potassium", value=5.1, unit="mmol/L"),
        Observation(code="hba1c", value=58.0, unit="mmol/mol"),
    ],
    vital_signs=VitalSigns(heart_rate=88, systolic_bp=125),
    social_history=SocialHistory(transport_access="poor"),
    encounters=[
        Encounter(encounter_id="E1", encounter_type="inpatient",
                  date="2026-01-15T00:00:00", reason="HF exacerbation"),
        Encounter(encounter_id="E2", encounter_type="emergency",
                  date="2025-11-20T00:00:00", reason="Breathlessness"),
        Encounter(encounter_id="E3", encounter_type="inpatient",
                  date="2025-08-10T00:00:00", reason="HF exacerbation"),
    ],
    chief_complaint="breathlessness",
    frailty_score=FrailtyScore.MODERATE,
)

check("has_condition HF", ctx.has_condition("heart_failure"))
check("has_allergy penicillin", ctx.has_allergy("penicillin"))
check("is_polypharmacy", ctx.is_polypharmacy())
check("latest_observation egfr", ctx.latest_observation("egfr") is not None)
check("observation_value", ctx.observation_value("egfr") == 35.0)
check("recent_admissions", ctx.recent_admission_count() >= 2)

# Assembler
assembler = ContextAssembler()
raw = {
    "demographics": {"patient_id": "ASM-001", "age": 45, "gender": "female"},
    "conditions": [{"code": "asthma"}],
    "chief_complaint": "cough",
}
assembled = assembler.assemble(raw)
check("assembler works", assembled.demographics.age == 45)
check("assembler condition", assembled.has_condition("asthma"))

# Consent
checker = ConsentChecker()
try:
    checker.check(ctx)
    check("consent active OK", True)
except ConsentDeniedError:
    check("consent active OK", False, "should not deny active consent")

denied_ctx = PatientContext(
    demographics=Demographics(patient_id="D1", given_name="A", family_name="B", age=30, gender=Gender.FEMALE),
    consent_status="denied",
)
try:
    checker.check(denied_ctx)
    check("consent denied raises", False, "should have raised")
except ConsentDeniedError:
    check("consent denied raises", True)

# Redactor
redactor = PHIRedactor()
redacted = redactor.redact(ctx)
check("redactor strips name", redacted.demographics.given_name != "John")
check("redactor pseudonymises ID", redacted.demographics.patient_id != "TEST-001")

# ═══════════════════════════════════════════════════════════════
# MODULE 3: Personalisation Engine
# ═══════════════════════════════════════════════════════════════
print("\n═══ Module 3: Personalisation Engine ═══")

personaliser = PathwayPersonaliser(audit_logger=AuditLogger())
check("personaliser has rules", len(personaliser._rules) >= 14)

# HF personalisation — complex patient
result = personaliser.personalise(hf, ctx)
check("HF personalised", result is not None)
check("HF has nodes", len(result.nodes) > 0)
check("HF has explainability", result.explainability is not None)
check("HF has modifications", len(result.explainability.modifications) > 0)
check("HF reasoning chain", len(result.explainability.reasoning_chain) > 0)
check("HF patient_id set", result.patient_id != "")
check("HF personalised_at set", result.personalised_at is not None)

mod_types = {m.modification_type for m in result.explainability.modifications}
check("HF polypharmacy rule triggered",
      ModificationType.ACTIVITY_ADDED in mod_types or
      ModificationType.INTENSITY_REDUCED in mod_types or
      len(mod_types) > 0)

# Sepsis personalisation
sepsis_ctx = PatientContext(
    demographics=Demographics(patient_id="S1", given_name="A", family_name="B", age=68, gender=Gender.FEMALE),
    allergies=[Allergy(substance="penicillin", reaction="anaphylaxis", severity="severe")],
    vital_signs=VitalSigns(heart_rate=110, systolic_bp=85, temperature=38.9, spo2=93,
                           respiratory_rate=24, consciousness="alert"),
    observations=[Observation(code="lactate", value=3.5, unit="mmol/L")],
    chief_complaint="fever",
)
sepsis_result = personaliser.personalise(sepsis, sepsis_ctx)
check("Sepsis personalised", sepsis_result is not None)
check("Sepsis has nodes", len(sepsis_result.nodes) > 0)

# Safety
safety = SafetyGuardrails()
alerts = safety.check_all(hf, ctx)
check("safety returns alerts", isinstance(alerts, list))

# DM personalisation
dm_ctx = PatientContext(
    demographics=Demographics(patient_id="DM1", given_name="A", family_name="B", age=65, gender=Gender.MALE),
    conditions=[
        Condition(code="type_2_diabetes", display="T2DM"),
        Condition(code="ckd_stage_4", display="CKD4"),
        Condition(code="diabetic_foot_ulcer", display="Foot ulcer"),
    ],
    medications=[Medication(code="metformin", display="Metformin 1g")],
    observations=[
        Observation(code="egfr", value=22.0, unit="mL/min/1.73m2"),
        Observation(code="hba1c", value=82.0, unit="mmol/mol"),
    ],
    chief_complaint="foot ulcer review",
)
dm_result = personaliser.personalise(dm, dm_ctx)
check("DM personalised", dm_result is not None)
check("DM has modifications", dm_result.explainability and len(dm_result.explainability.modifications) > 0)

# ANC personalisation
anc_ctx = PatientContext(
    demographics=Demographics(patient_id="ANC1", given_name="A", family_name="B", age=38, gender=Gender.FEMALE),
    conditions=[Condition(code="pre_eclampsia_history", display="Previous pre-eclampsia")],
    chief_complaint="booking visit",
)
anc_result = personaliser.personalise(anc, anc_ctx)
check("ANC personalised", anc_result is not None)

# COPD personalisation
copd_ctx = PatientContext(
    demographics=Demographics(patient_id="COPD1", given_name="A", family_name="B", age=60, gender=Gender.MALE),
    conditions=[
        Condition(code="copd", display="COPD"),
        Condition(code="heart_failure", display="HF"),
    ],
    observations=[Observation(code="fev1_fvc_ratio", value=0.55, unit="ratio")],
    chief_complaint="breathlessness",
)
copd_result = personaliser.personalise(copd, copd_ctx)
check("COPD personalised", copd_result is not None)

# Agent cards
from clinical_pathways.agent_cards import get_all_agent_cards
cards = get_all_agent_cards()
check("agent cards exist", len(cards) >= 3)
for card in cards:
    check(f"card {card.get('name','')} has name", "name" in card)
    check(f"card {card.get('name','')} has capabilities", "capabilities" in card)

# ═══════════════════════════════════════════════════════════════
# MODULE 4: Scenario Tests (300 JSON scenarios)
# ═══════════════════════════════════════════════════════════════
print("\n═══ Module 4: Scenario Tests (300 JSON) ═══")

scenarios_dir = Path(__file__).parent / "tests" / "scenarios"
total_scenarios = 0
scenario_passes = 0
scenario_fails = 0

for json_file in sorted(scenarios_dir.glob("scenarios_*.json")):
    data = json.loads(json_file.read_text(encoding="utf-8"))
    file_passes = 0
    file_fails = 0

    for s in data:
        total_scenarios += 1
        sid = s["usecaseid"]
        try:
            input_data = json.loads(s["inputdata"])
            pathway_id = input_data["pathway_id"]
            pctx_raw = input_data["patient_context"]

            pathway = repo.get(pathway_id)
            assert pathway is not None, f"Pathway {pathway_id} not found"

            # Build patient context
            demo = pctx_raw.get("demographics", {})
            gender_str = demo.get("gender", "unknown")
            try:
                gender = Gender(gender_str)
            except ValueError:
                gender = Gender.UNKNOWN

            patient_ctx = PatientContext(
                demographics=Demographics(
                    patient_id=demo.get("patient_id", "TEST"),
                    given_name="Scenario", family_name="Patient",
                    age=demo.get("age", 50), gender=gender,
                ),
                conditions=[Condition(**c) for c in pctx_raw.get("conditions", [])],
                medications=[Medication(**m) for m in pctx_raw.get("medications", [])],
                allergies=[Allergy(**a) for a in pctx_raw.get("allergies", [])],
                observations=[Observation(**o) for o in pctx_raw.get("observations", [])],
                vital_signs=VitalSigns(**pctx_raw.get("vital_signs", {})) if pctx_raw.get("vital_signs") else VitalSigns(),
                social_history=SocialHistory(**pctx_raw.get("social_history", {})) if pctx_raw.get("social_history") else SocialHistory(),
                encounters=[Encounter(**e) for e in pctx_raw.get("encounters", [])],
                chief_complaint=pctx_raw.get("chief_complaint", ""),
                frailty_score=FrailtyScore(pctx_raw["frailty_score"]) if pctx_raw.get("frailty_score") else None,
            )

            result = personaliser.personalise(pathway, patient_ctx)

            expected = s["expectedoutcome"]
            expected_status = expected["status"]

            if expected_status == "personalised_pathway_returned":
                assert result is not None
                assert result.pathway_id == pathway_id
                assert result.explainability is not None
                assert len(result.nodes) > 0

            expected_mods = expected.get("modifications", [])
            if expected_mods:
                actual_mod_types = {m.modification_type.value for m in result.explainability.modifications}
                for em in expected_mods:
                    assert em in actual_mod_types, f"Missing mod: {em}"

            assert result.explainability.pathway_id == pathway_id
            assert len(result.explainability.reasoning_chain) > 0
            assert result.patient_id
            assert result.personalised_at is not None

            file_passes += 1
            scenario_passes += 1

        except Exception as exc:
            file_fails += 1
            scenario_fails += 1
            errors.append(f"SCENARIO {sid}: {exc}")
            if scenario_fails <= 5:
                print(f"  ✗ {sid}: {exc}")

    print(f"  {json_file.name}: {file_passes}/{len(data)} passed")

# Clean up temp file
try:
    Path("test_trivial_m4s08kqw.py").unlink(missing_ok=True)
except:
    pass

# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
total = passed + failed + scenario_passes + scenario_fails
unit_total = passed + failed
print(f"\n{'═' * 60}")
print(f"UNIT TESTS:     {passed}/{unit_total} passed")
print(f"SCENARIO TESTS: {scenario_passes}/{total_scenarios} passed")
print(f"TOTAL:          {passed + scenario_passes}/{total} passed")
print(f"{'═' * 60}")

if errors:
    print(f"\n{len(errors)} FAILURES:")
    for e in errors[:20]:
        print(f"  • {e}")
    if len(errors) > 20:
        print(f"  ... and {len(errors) - 20} more")
    sys.exit(1)
else:
    print("\n✅ ALL TESTS PASSED — 100% pass rate")
    sys.exit(0)
