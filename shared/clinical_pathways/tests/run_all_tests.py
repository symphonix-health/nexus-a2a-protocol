#!/usr/bin/env python3
"""Standalone test runner — runs all test suites without pytest.

Validates 100% pass rate across:
  - Repository tests (19 tests)
  - Agent card tests (7 tests)
  - Context tests
  - Personaliser tests
  - Safety tests
  - Scenario tests (300 scenarios from JSON files)
"""

from __future__ import annotations

import importlib
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

# ── Bootstrap import path ────────────────────────────────────────

_pkg_dir = Path(__file__).resolve().parent.parent
_ws_dir = _pkg_dir.parent
if str(_ws_dir) not in sys.path:
    sys.path.insert(0, str(_ws_dir))

if "clinical_pathways" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "clinical_pathways",
        str(_pkg_dir / "__init__.py"),
        submodule_search_locations=[str(_pkg_dir)],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["clinical_pathways"] = mod
    spec.loader.exec_module(mod)

from clinical_pathways.agent_cards import (
    CONTEXT_ASSEMBLER_AGENT_CARD,
    PATHWAY_KNOWLEDGE_AGENT_CARD,
    PATHWAY_PERSONALISATION_AGENT_CARD,
    get_all_agent_cards,
)
from clinical_pathways.context.assembler import ContextAssembler
from clinical_pathways.context.consent import ConsentChecker, ConsentDeniedError
from clinical_pathways.context.models import (
    Allergy,
    Condition,
    Demographics,
    Encounter,
    FrailtyScore,
    Gender,
    Medication,
    Observation,
    PatientContext,
    SocialHistory,
    VitalSigns,
)
from clinical_pathways.context.redactor import PHIRedactor
from clinical_pathways.engine.audit import AuditLogger
from clinical_pathways.engine.models import ModificationType
from clinical_pathways.engine.personaliser import PathwayPersonaliser
from clinical_pathways.engine.safety import SafetyGuardrails
from clinical_pathways.loader import load_pathways
from clinical_pathways.repository import PathwayRepository

# ── Test infrastructure ──────────────────────────────────────────

passed = 0
failed = 0
errors: list[str] = []


def run_test(name: str, fn):
    global passed, failed
    try:
        fn()
        passed += 1
    except AssertionError as e:
        failed += 1
        errors.append(f"FAIL: {name} — {e}")
        print(f"  FAIL: {name} — {e}")
    except Exception as e:
        failed += 1
        errors.append(f"ERROR: {name} — {e}")
        print(f"  ERROR: {name} — {e}")
        traceback.print_exc()


# ── Shared fixtures ──────────────────────────────────────────────

repo = load_pathways()
personaliser = PathwayPersonaliser(audit_logger=AuditLogger())
assembler = ContextAssembler()
safety = SafetyGuardrails()

SCENARIOS_DIR = Path(__file__).parent / "scenarios"


def make_patient_context(
    *,
    patient_id="TEST-001",
    age=55,
    gender="male",
    conditions=None,
    medications=None,
    allergies=None,
    observations=None,
    vital_signs=None,
    chief_complaint="",
    frailty_score=None,
    social_history=None,
    encounters=None,
):
    conditions = conditions or []
    medications = medications or []
    allergies = allergies or []
    observations = observations or []
    vital_signs = vital_signs or {}
    social_history = social_history or {}
    encounters = encounters or []

    gender_val = Gender(gender) if gender in [g.value for g in Gender] else Gender.UNKNOWN
    frailty = None
    if frailty_score:
        try:
            frailty = FrailtyScore(frailty_score)
        except ValueError:
            pass

    return PatientContext(
        demographics=Demographics(
            patient_id=patient_id,
            given_name="Test",
            family_name="Patient",
            age=age,
            gender=gender_val,
        ),
        conditions=[Condition(**c) for c in conditions],
        medications=[Medication(**m) for m in medications],
        allergies=[Allergy(**a) for a in allergies],
        observations=[Observation(**o) for o in observations],
        vital_signs=VitalSigns(**vital_signs),
        social_history=SocialHistory(**social_history),
        encounters=[Encounter(**e) for e in encounters],
        chief_complaint=chief_complaint,
        frailty_score=frailty,
    )


# ════════════════════════════════════════════════════════════════════
# 1. REPOSITORY TESTS
# ════════════════════════════════════════════════════════════════════

def assert_true(cond, msg=""):
    assert cond, msg


def assert_eq(a, b, msg=""):
    assert a == b, msg or f"{a!r} != {b!r}"


def assert_in(item, container, msg=""):
    assert item in container, msg or f"{item!r} not in {container!r}"


def assert_none(val, msg=""):
    assert val is None, msg or f"Expected None, got {val!r}"


def assert_not_none(val, msg=""):
    assert val is not None, msg or f"Expected not None"


print("\n=== Repository Tests ===")

run_test("repo_load_all", lambda: assert_true(repo.count >= 4))

run_test("repo_get_heart_failure", lambda: (
    assert_not_none(repo.get("nice-ng106-heart-failure")),
    assert_eq(repo.get("nice-ng106-heart-failure").title, "Chronic Heart Failure in Adults: Diagnosis and Management"),
    assert_eq(repo.get("nice-ng106-heart-failure").source_authority, "NICE"),
    assert_eq(repo.get("nice-ng106-heart-failure").country, "GB"),
))

run_test("repo_get_copd", lambda: (
    assert_not_none(repo.get("nice-ng115-copd")),
    assert_true(
        "Obstructive Pulmonary" in repo.get("nice-ng115-copd").title or "COPD" in repo.get("nice-ng115-copd").description,
    ),
))

run_test("repo_get_diabetes", lambda: (
    assert_not_none(repo.get("nice-ng28-diabetes-type2")),
    assert_true("Type 2 Diabetes" in repo.get("nice-ng28-diabetes-type2").title),
))

run_test("repo_get_sepsis", lambda: (
    assert_not_none(repo.get("nice-ng51-sepsis")),
    assert_true("Sepsis" in repo.get("nice-ng51-sepsis").title),
))

run_test("repo_get_maternal", lambda: (
    assert_not_none(repo.get("who-maternal-anc")),
    assert_eq(repo.get("who-maternal-anc").source_authority, "WHO"),
))

run_test("repo_get_nonexistent", lambda: assert_none(repo.get("nonexistent-pathway")))

run_test("repo_list_active_gb", lambda: assert_true(len(repo.list_active(country="GB")) >= 4))
run_test("repo_list_active_int", lambda: assert_true(len(repo.list_active(country="INT")) >= 1))
run_test("repo_list_by_authority_nice", lambda: assert_true(len(repo.list_by_authority("NICE")) >= 4))
run_test("repo_list_by_authority_who", lambda: assert_true(len(repo.list_by_authority("WHO")) >= 1))

run_test("repo_search_heart", lambda: (
    assert_true(len(repo.search("heart")) >= 1),
    assert_true(any("heart" in r.title.lower() for r in repo.search("heart"))),
))

run_test("repo_search_diabetes", lambda: assert_true(len(repo.search("diabetes")) >= 1))
run_test("repo_search_no_results", lambda: assert_eq(len(repo.search("xyznonexistent")), 0))

run_test("repo_all_ids", lambda: (
    assert_in("nice-ng106-heart-failure", repo.all_ids()),
    assert_in("nice-ng51-sepsis", repo.all_ids()),
))

def test_pathway_has_nodes():
    for pid in repo.all_ids():
        p = repo.get(pid)
        assert_not_none(p)
        assert_true(len(p.nodes) > 0, f"Pathway {pid} has no nodes")

run_test("repo_pathway_has_nodes", test_pathway_has_nodes)

def test_pathway_has_entry_node():
    for pid in repo.all_ids():
        p = repo.get(pid)
        assert_not_none(p.entry_node(), f"Pathway {pid} has no entry node")

run_test("repo_pathway_has_entry_node", test_pathway_has_entry_node)

def test_pathway_has_exit_node():
    for pid in repo.all_ids():
        p = repo.get(pid)
        assert_true(len(p.exit_nodes()) > 0, f"Pathway {pid} has no exit nodes")

run_test("repo_pathway_has_exit_node", test_pathway_has_exit_node)


# ════════════════════════════════════════════════════════════════════
# 2. AGENT CARD TESTS
# ════════════════════════════════════════════════════════════════════

print("\n=== Agent Card Tests ===")

run_test("agent_cards_count", lambda: assert_eq(len(get_all_agent_cards()), 3))
run_test("knowledge_card_id", lambda: assert_eq(PATHWAY_KNOWLEDGE_AGENT_CARD["agent_id"], "pathway-knowledge-agent"))
run_test("knowledge_card_provider", lambda: assert_eq(PATHWAY_KNOWLEDGE_AGENT_CARD["provider"], "Symphonix-Health"))

run_test("personalisation_card_rules", lambda: (
    assert_eq(PATHWAY_PERSONALISATION_AGENT_CARD["agent_id"], "pathway-personalisation-agent"),
    assert_true(len(PATHWAY_PERSONALISATION_AGENT_CARD["personalisation_rules"]) >= 15),
    assert_true(PATHWAY_PERSONALISATION_AGENT_CARD["trust_metadata"]["explainability"]),
    assert_true(PATHWAY_PERSONALISATION_AGENT_CARD["trust_metadata"]["clinician_in_the_loop"]),
))

run_test("context_card_phi", lambda: (
    assert_eq(CONTEXT_ASSEMBLER_AGENT_CARD["agent_id"], "context-assembler-agent"),
    assert_true(CONTEXT_ASSEMBLER_AGENT_CARD["trust_metadata"]["consent_checking"]),
    assert_true(CONTEXT_ASSEMBLER_AGENT_CARD["trust_metadata"]["phi_redaction"]),
))

def test_all_cards_required_fields():
    for card in get_all_agent_cards():
        for field in ("agent_id", "name", "description", "capabilities", "interoperability", "trust_metadata"):
            assert_in(field, card, f"Card {card.get('agent_id', '?')} missing {field}")

run_test("agent_cards_required_fields", test_all_cards_required_fields)

def test_all_cards_a2a():
    for card in get_all_agent_cards():
        assert_eq(card["interoperability"]["protocol"], "a2a")

run_test("agent_cards_a2a_protocol", test_all_cards_a2a)


# ════════════════════════════════════════════════════════════════════
# 3. PERSONALISER TESTS
# ════════════════════════════════════════════════════════════════════

print("\n=== Personaliser Tests ===")

def test_personalise_simple():
    pathway = repo.get("nice-ng106-heart-failure")
    ctx = make_patient_context(age=55, chief_complaint="breathlessness")
    result = personaliser.personalise(pathway, ctx)
    assert_not_none(result)
    assert_eq(result.pathway_id, "nice-ng106-heart-failure")
    assert_true(len(result.nodes) > 0)
    assert_not_none(result.explainability)

run_test("personalise_simple_hf", test_personalise_simple)

def test_personalise_complex_hf():
    pathway = repo.get("nice-ng106-heart-failure")
    ctx = make_patient_context(
        age=72,
        conditions=[
            {"code": "heart_failure", "display": "CHF"},
            {"code": "ckd_stage_3", "display": "CKD 3"},
        ],
        medications=[
            {"code": "ramipril"}, {"code": "bisoprolol"}, {"code": "furosemide"},
            {"code": "spironolactone"}, {"code": "metformin"}, {"code": "atorvastatin"},
        ],
        observations=[
            {"code": "egfr", "value": 35.0, "unit": "mL/min/1.73m2"},
            {"code": "nt_pro_bnp", "value": 1800.0, "unit": "ng/L"},
        ],
        chief_complaint="breathlessness",
        frailty_score="moderate",
    )
    result = personaliser.personalise(pathway, ctx)
    assert_not_none(result)
    mod_types = {m.modification_type.value for m in result.explainability.modifications}
    assert_true(len(mod_types) > 0, "Expected some modifications for complex patient")

run_test("personalise_complex_hf", test_personalise_complex_hf)

def test_personalise_sepsis():
    pathway = repo.get("nice-ng51-sepsis")
    ctx = make_patient_context(
        age=68,
        conditions=[{"code": "urinary_tract_infection", "display": "UTI"}],
        allergies=[{"substance": "penicillin", "category": "medication", "reaction": "anaphylaxis", "severity": "severe"}],
        vital_signs={
            "heart_rate": 110, "systolic_bp": 85, "respiratory_rate": 24,
            "temperature": 38.9, "spo2": 93, "consciousness": "alert",
        },
        observations=[{"code": "lactate", "value": 3.5, "unit": "mmol/L"}],
        chief_complaint="fever",
    )
    result = personaliser.personalise(pathway, ctx)
    assert_not_none(result)

run_test("personalise_sepsis", test_personalise_sepsis)

def test_personalise_diabetes_ckd():
    pathway = repo.get("nice-ng28-diabetes-type2")
    ctx = make_patient_context(
        age=65,
        conditions=[
            {"code": "type_2_diabetes", "display": "T2DM"},
            {"code": "ckd_stage_4", "display": "CKD 4"},
            {"code": "diabetic_foot_ulcer", "display": "Foot ulcer"},
        ],
        medications=[
            {"code": "metformin"}, {"code": "gliclazide"}, {"code": "ramipril"},
            {"code": "amlodipine"}, {"code": "atorvastatin"},
        ],
        observations=[
            {"code": "egfr", "value": 22.0, "unit": "mL/min/1.73m2"},
            {"code": "hba1c", "value": 82.0, "unit": "mmol/mol"},
        ],
        chief_complaint="foot ulcer review",
    )
    result = personaliser.personalise(pathway, ctx)
    assert_not_none(result)

run_test("personalise_diabetes_ckd", test_personalise_diabetes_ckd)

def test_personalise_maternal():
    pathway = repo.get("who-maternal-anc")
    ctx = make_patient_context(
        patient_id="MAT-001", age=42, gender="female",
        conditions=[
            {"code": "pregnancy", "display": "Pregnancy"},
            {"code": "pre_eclampsia", "display": "Pre-eclampsia"},
        ],
        chief_complaint="pregnancy booking",
    )
    result = personaliser.personalise(pathway, ctx)
    assert_not_none(result)

run_test("personalise_maternal", test_personalise_maternal)


# ════════════════════════════════════════════════════════════════════
# 4. CONTEXT ASSEMBLY TESTS
# ════════════════════════════════════════════════════════════════════

print("\n=== Context Assembly Tests ===")

def test_assembler_basic():
    raw = {
        "demographics": {"patient_id": "P1", "given_name": "Test", "family_name": "User", "age": 55, "gender": "male"},
        "conditions": [{"code": "heart_failure", "display": "HF"}],
        "medications": [{"code": "ramipril", "display": "Ramipril 5mg"}],
        "chief_complaint": "breathlessness",
    }
    ctx = assembler.assemble(raw)
    assert_eq(ctx.demographics.patient_id, "P1")
    assert_eq(ctx.age, 55)
    assert_true(ctx.has_condition("heart_failure"))

run_test("assembler_basic", test_assembler_basic)

def test_redactor():
    ctx = make_patient_context(patient_id="NHS-12345", age=55)
    redactor = PHIRedactor()
    redacted = redactor.redact(ctx)
    assert_true(redacted.demographics.patient_id != "NHS-12345", "Patient ID not redacted")
    assert_eq(redacted.demographics.given_name, "[REDACTED]")
    assert_eq(redacted.demographics.family_name, "[REDACTED]")

run_test("redactor", test_redactor)

def test_consent_checker():
    checker = ConsentChecker()
    ctx = make_patient_context(age=55)
    # Should not raise for direct care
    checked = checker.check(ctx, purpose="direct_care")
    assert_not_none(checked)

run_test("consent_checker", test_consent_checker)


# ════════════════════════════════════════════════════════════════════
# 5. SAFETY TESTS
# ════════════════════════════════════════════════════════════════════

print("\n=== Safety Tests ===")

def test_safety_critical_potassium():
    pathway = repo.get("nice-ng106-heart-failure")
    ctx = make_patient_context(
        age=70,
        conditions=[{"code": "heart_failure"}],
        observations=[{"code": "potassium", "value": 6.5, "unit": "mmol/L"}],
    )
    mods = safety.check_all(pathway, ctx)
    mod_types = {m.modification_type.value for m in mods}
    assert_in("safety_override", mod_types, f"Expected safety_override for K+=6.5, got {mod_types}")

run_test("safety_critical_potassium", test_safety_critical_potassium)

def test_safety_triple_whammy():
    pathway = repo.get("nice-ng106-heart-failure")
    ctx = make_patient_context(
        age=68,
        conditions=[{"code": "heart_failure"}],
        medications=[
            {"code": "ramipril"}, {"code": "spironolactone"}, {"code": "ibuprofen"},
        ],
        observations=[{"code": "egfr", "value": 55.0, "unit": "mL/min/1.73m2"}],
    )
    mods = safety.check_all(pathway, ctx)
    assert_true(len(mods) > 0, "Expected safety modifications for triple whammy")

run_test("safety_triple_whammy", test_safety_triple_whammy)


# ════════════════════════════════════════════════════════════════════
# 6. SCENARIO TESTS (300 scenarios from JSON files)
# ════════════════════════════════════════════════════════════════════

print("\n=== Scenario Tests (300 scenarios) ===")

scenario_files = sorted(SCENARIOS_DIR.glob("scenarios_*.json"))
if not scenario_files:
    print("  WARNING: No scenario files found! Run generate_scenarios.py first.")
else:
    for json_file in scenario_files:
        data = json.loads(json_file.read_text(encoding="utf-8"))
        file_pass = 0
        file_fail = 0

        for scenario in data:
            sid = scenario["usecaseid"]

            def run_scenario(s=scenario):
                input_data = json.loads(s["inputdata"])
                pathway_id = input_data["pathway_id"]
                pctx_raw = input_data["patient_context"]

                # Pathway must exist
                pathway = repo.get(pathway_id)
                assert_not_none(pathway, f"Pathway {pathway_id} not found")

                # Build patient context
                demo = pctx_raw.get("demographics", {})
                gender_str = demo.get("gender", "unknown")
                try:
                    gender = Gender(gender_str)
                except ValueError:
                    gender = Gender.UNKNOWN

                frailty = None
                fs = pctx_raw.get("frailty_score", "")
                if fs:
                    try:
                        frailty = FrailtyScore(fs)
                    except ValueError:
                        pass

                ctx = PatientContext(
                    demographics=Demographics(
                        patient_id=demo.get("patient_id", "TEST"),
                        given_name="Scenario", family_name="Patient",
                        age=demo.get("age", 50), gender=gender,
                    ),
                    conditions=[Condition(**c) for c in pctx_raw.get("conditions", [])],
                    medications=[Medication(**m) for m in pctx_raw.get("medications", [])],
                    allergies=[Allergy(**a) for a in pctx_raw.get("allergies", [])],
                    observations=[Observation(**o) for o in pctx_raw.get("observations", [])],
                    vital_signs=VitalSigns(**pctx_raw.get("vital_signs", {})),
                    social_history=SocialHistory(**pctx_raw.get("social_history", {})),
                    encounters=[Encounter(**e) for e in pctx_raw.get("encounters", [])],
                    chief_complaint=pctx_raw.get("chief_complaint", ""),
                    frailty_score=frailty,
                )

                # Personalise
                result = personaliser.personalise(pathway, ctx)
                assert_not_none(result)
                assert_eq(result.pathway_id, pathway_id)
                assert_true(len(result.nodes) > 0, f"{s['usecaseid']}: No nodes")
                assert_not_none(result.explainability)
                assert_true(len(result.explainability.reasoning_chain) > 0)
                assert_true(bool(result.patient_id), "Missing patient_id")

                # Validate expected modifications
                expected_mods = s["expectedoutcome"].get("modifications", [])
                if expected_mods:
                    actual_mod_types = {m.modification_type.value for m in result.explainability.modifications}
                    for em in expected_mods:
                        assert_in(em, actual_mod_types,
                                  f"{s['usecaseid']}: Expected mod '{em}', got {actual_mod_types}")

            run_test(sid, run_scenario)

        print(f"  {json_file.name}: done")


# ════════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════════

total = passed + failed
print(f"\n{'='*60}")
print(f"TOTAL: {total} tests | PASSED: {passed} | FAILED: {failed}")
print(f"{'='*60}")

if errors:
    print(f"\nFailures ({len(errors)}):")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("\nALL TESTS PASS — 100% pass rate achieved!")
    sys.exit(0)
