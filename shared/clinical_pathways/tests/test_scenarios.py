"""Scenario-driven tests — runs 300 generated JSON scenarios against the personaliser.

Each scenario is loaded from the JSON files in tests/scenarios/ and exercises
the full personalisation pipeline: pathway lookup → context assembly → personalise → validate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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

SCENARIOS_DIR = Path(__file__).parent / "scenarios"

# ── Load all scenario files ──────────────────────────────────────

def _load_scenarios() -> list[tuple[str, dict]]:
    """Load all scenario JSON files and return (id, scenario) pairs.

    Excludes integration scenarios — those are tested by test_integration_scenarios.py.
    """
    pairs = []
    for json_file in sorted(SCENARIOS_DIR.glob("scenarios_*.json")):
        if "integration" in json_file.name:
            continue
        data = json.loads(json_file.read_text(encoding="utf-8"))
        for s in data:
            pairs.append((s["usecaseid"], s))
    return pairs


ALL_SCENARIOS = _load_scenarios()


def _build_patient_context(pctx: dict) -> PatientContext:
    """Build a PatientContext from a scenario's patient_context dict."""
    demo = pctx.get("demographics", {})
    gender_str = demo.get("gender", "unknown")
    try:
        gender = Gender(gender_str)
    except ValueError:
        gender = Gender.UNKNOWN

    conditions = [
        Condition(**c) for c in pctx.get("conditions", [])
    ]
    medications = [
        Medication(**m) for m in pctx.get("medications", [])
    ]

    raw_allergies = pctx.get("allergies", [])
    allergies = []
    for a in raw_allergies:
        allergies.append(Allergy(**a))

    observations = [
        Observation(**o) for o in pctx.get("observations", [])
    ]

    vs_data = pctx.get("vital_signs", {})
    vital_signs = VitalSigns(**vs_data) if vs_data else VitalSigns()

    frailty_str = pctx.get("frailty_score", "")
    frailty = None
    if frailty_str:
        try:
            frailty = FrailtyScore(frailty_str)
        except ValueError:
            pass

    sh_data = pctx.get("social_history", {})
    social_history = SocialHistory(**sh_data) if sh_data else SocialHistory()

    encounters = [
        Encounter(**e) for e in pctx.get("encounters", [])
    ]

    return PatientContext(
        demographics=Demographics(
            patient_id=demo.get("patient_id", "TEST"),
            given_name="Scenario",
            family_name="Patient",
            age=demo.get("age", 50),
            gender=gender,
        ),
        conditions=conditions,
        medications=medications,
        allergies=allergies,
        observations=observations,
        vital_signs=vital_signs,
        social_history=social_history,
        encounters=encounters,
        chief_complaint=pctx.get("chief_complaint", ""),
        frailty_score=frailty,
    )


# ── Parametrised test ────────────────────────────────────────────

@pytest.fixture(scope="module")
def repo():
    return load_pathways()


@pytest.fixture(scope="module")
def personaliser():
    return PathwayPersonaliser(audit_logger=AuditLogger())


@pytest.mark.parametrize(
    "scenario_id,scenario",
    ALL_SCENARIOS,
    ids=[s[0] for s in ALL_SCENARIOS],
)
def test_scenario(scenario_id: str, scenario: dict, repo, personaliser):
    """Run a single scenario through the personaliser and validate the outcome."""
    input_data = json.loads(scenario["inputdata"])
    pathway_id = input_data["pathway_id"]
    pctx_raw = input_data["patient_context"]

    # 1. Pathway lookup
    pathway = repo.get(pathway_id)

    # 2. Validate outcome expectations
    expected = scenario["expectedoutcome"]
    expected_status = expected["status"]

    # Handle negative test: pathway not found
    if expected_status == "pathway_not_found":
        assert pathway is None, f"Pathway {pathway_id} should not exist but was found"
        return

    assert pathway is not None, f"Pathway {pathway_id} not found in repository"

    # 3. Build patient context
    ctx = _build_patient_context(pctx_raw)

    # 4. Personalise — should not raise
    result = personaliser.personalise(pathway, ctx)

    if expected_status == "personalised_pathway_returned":
        assert result is not None
        assert result.pathway_id == pathway_id
        assert result.explainability is not None
        assert len(result.nodes) > 0

    # 5. Validate expected modifications (if specified)
    expected_mods = expected.get("modifications", [])
    if expected_mods:
        actual_mod_types = {
            m.modification_type.value
            for m in result.explainability.modifications
        }
        for expected_mod in expected_mods:
            assert expected_mod in actual_mod_types, (
                f"Scenario {scenario_id}: expected modification '{expected_mod}' "
                f"not found. Actual: {actual_mod_types}"
            )

    # 6. Verify explainability is populated
    assert result.explainability.pathway_id == pathway_id
    assert len(result.explainability.reasoning_chain) > 0

    # 7. Verify audit-relevant fields
    assert result.patient_id  # pseudo-anonymised
    assert result.personalised_at is not None

    # 8. Verify deviation register (if present in result)
    if result.deviation_register is not None:
        dev_reg = result.deviation_register
        assert dev_reg.pathway_id == pathway_id
        assert dev_reg.patient_id_pseudonymised == result.patient_id
        assert dev_reg.total_deviations == len(dev_reg.deviations)

        # Verify deviation count matches modifications count
        assert dev_reg.total_deviations == result.explainability.modification_count

        # Verify each deviation has standard vs individualised comparison
        for dev in dev_reg.deviations:
            assert dev.standard_pathway_step, f"Deviation {dev.deviation_id} missing standard_pathway_step"
            assert dev.individualised_step, f"Deviation {dev.deviation_id} missing individualised_step"
            assert dev.reason, f"Deviation {dev.deviation_id} missing reason"
            assert dev.severity, f"Deviation {dev.deviation_id} missing severity"

        # Validate expected deviation count if specified
        expected_dev_count = expected.get("deviation_count")
        if expected_dev_count is not None:
            assert dev_reg.total_deviations == expected_dev_count, (
                f"Scenario {scenario_id}: expected {expected_dev_count} deviations, "
                f"got {dev_reg.total_deviations}"
            )

        # Validate expected requires_clinician_signoff if specified
        expected_signoff = expected.get("requires_clinician_signoff")
        if expected_signoff is not None:
            assert dev_reg.requires_any_clinician_signoff == expected_signoff, (
                f"Scenario {scenario_id}: expected requires_clinician_signoff={expected_signoff}, "
                f"got {dev_reg.requires_any_clinician_signoff}"
            )
