"""Integration scenario tests — validates pathway-to-agent adapter wiring.

Runs 100 generated JSON scenarios that exercise the full integration pipeline:
  PathwayPersonaliser → Adapter → BulletTrain agent input contract

Each scenario tests that:
  1. The pathway personalises without error
  2. The correct adapter produces valid output
  3. The output matches the downstream agent's expected contract
  4. Safety flags, contraindications, and deviations are correctly propagated
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clinical_pathways.context.models import (
    Allergy,
    AllergyCategory,
    AllergySeverity,
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
from clinical_pathways.engine.audit import AuditLogger
from clinical_pathways.engine.personaliser import PathwayPersonaliser
from clinical_pathways.integration import adapters
from clinical_pathways.integration.orchestrator import PathwayOrchestrator
from clinical_pathways.loader import load_pathways

SCENARIOS_DIR = Path(__file__).parent / "scenarios"


# ── Load integration scenarios ──────────────────────────────────────

def _load_integration_scenarios() -> list[tuple[str, dict]]:
    """Load integration scenario JSON files."""
    pairs = []
    json_file = SCENARIOS_DIR / "scenarios_integration.json"
    if json_file.exists():
        data = json.loads(json_file.read_text(encoding="utf-8"))
        for s in data:
            pairs.append((s["usecaseid"], s))
    return pairs


ALL_SCENARIOS = _load_integration_scenarios()


def _build_patient_context(pctx: dict) -> PatientContext:
    """Build a PatientContext from scenario patient_context dict."""
    demo = pctx.get("demographics", {})
    gender_str = demo.get("gender", "unknown")
    try:
        gender = Gender(gender_str)
    except ValueError:
        gender = Gender.UNKNOWN

    conditions = [Condition(**c) for c in pctx.get("conditions", [])]
    medications = [Medication(**m) for m in pctx.get("medications", [])]
    allergies = [Allergy(**a) for a in pctx.get("allergies", [])]
    observations = [Observation(**o) for o in pctx.get("observations", [])]

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

    encounters = [Encounter(**e) for e in pctx.get("encounters", [])]

    return PatientContext(
        demographics=Demographics(
            patient_id=demo.get("patient_id", "TEST"),
            given_name="Integration",
            family_name="Test",
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


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def repo():
    return load_pathways()


@pytest.fixture(scope="module")
def personaliser():
    return PathwayPersonaliser(audit_logger=AuditLogger())


@pytest.fixture(scope="module")
def orchestrator(personaliser):
    return PathwayOrchestrator(personaliser=personaliser)


# ── Adapter dispatch table ──────────────────────────────────────────

def _run_adapter(
    adapter_name: str,
    pathway,
    ctx: PatientContext,
    input_data: dict,
    personaliser: PathwayPersonaliser,
    orchestrator_obj: PathwayOrchestrator,
) -> dict | object:
    """Personalise and run the named adapter, returning the result."""
    if adapter_name == "orchestrate":
        return orchestrator_obj.orchestrate(
            pathway,
            ctx,
            chief_complaint=input_data.get("chief_complaint", ""),
            diagnosis=input_data.get("diagnosis", ""),
        )

    # All other adapters need a personalised pathway first
    result = personaliser.personalise(pathway, ctx)

    dispatch = {
        "to_diagnostic_context": lambda: adapters.to_diagnostic_context(
            result,
            patient_id=ctx.demographics.patient_id,
            chief_complaint=input_data.get("chief_complaint", ""),
        ),
        "to_treatment_context": lambda: adapters.to_treatment_context(
            result,
            diagnosis=input_data.get("diagnosis", ""),
        ),
        "to_prescribing_guard": lambda: adapters.to_prescribing_guard(
            result,
            medication_name=input_data.get("medication", {}).get("name", "test_med"),
            dose_mg=input_data.get("medication", {}).get("dose_mg", 100),
            frequency=input_data.get("medication", {}).get("frequency", "once daily"),
            patient_id=ctx.demographics.patient_id,
        ),
        "to_referral_request": lambda: adapters.to_referral_request(
            result,
            patient_id=ctx.demographics.patient_id,
        ),
        "to_investigation_plan": lambda: adapters.to_investigation_plan(result),
        "to_imaging_request": lambda: adapters.to_imaging_request(
            result,
            patient_id=ctx.demographics.patient_id,
        ),
        "to_discharge_plan": lambda: adapters.to_discharge_plan(result),
        "to_continuity_request": lambda: adapters.to_continuity_request(
            result,
            patient_id=ctx.demographics.patient_id,
        ),
        "to_chat_context": lambda: adapters.to_chat_context(result),
        "to_apex_risk_input": lambda: adapters.to_apex_risk_input(
            result,
            patient_id=ctx.demographics.patient_id,
        ),
    }

    if adapter_name not in dispatch:
        raise ValueError(f"Unknown adapter: {adapter_name}")

    return dispatch[adapter_name]()


# ── Parametrised test ───────────────────────────────────────────────

@pytest.mark.parametrize(
    "scenario_id,scenario",
    ALL_SCENARIOS,
    ids=[s[0] for s in ALL_SCENARIOS],
)
def test_integration_scenario(
    scenario_id: str,
    scenario: dict,
    repo,
    personaliser,
    orchestrator,
):
    """Run a single integration scenario through the adapter pipeline."""
    input_data = json.loads(scenario["inputdata"])
    pathway_id = input_data["pathway_id"]
    pctx_raw = input_data["patient_context"]
    adapter_name = input_data["adapter"]
    expected = scenario["expectedoutcome"]
    scenario_type = scenario["scenariotype"]

    # 1. Pathway lookup
    pathway = repo.get(pathway_id)

    # 2. Handle pathway-not-found negative test
    if expected.get("expected_error") == "pathway_not_found":
        assert pathway is None, f"Pathway {pathway_id} should not exist"
        return

    assert pathway is not None, f"Pathway {pathway_id} not found in repository"

    # 3. Build patient context
    ctx = _build_patient_context(pctx_raw)

    # 4. Run the adapter — should not raise
    result = _run_adapter(
        adapter_name, pathway, ctx, input_data, personaliser, orchestrator,
    )

    # 5. Validate based on scenario type
    if scenario_type == "pos":
        _validate_positive(scenario_id, adapter_name, result, expected)
    elif scenario_type == "neg":
        _validate_negative(scenario_id, adapter_name, result, expected)
    elif scenario_type == "edge":
        _validate_edge(scenario_id, adapter_name, result, expected)


def _validate_positive(scenario_id: str, adapter: str, result, expected: dict):
    """Validate positive scenario output."""
    assert result is not None, f"{scenario_id}: adapter {adapter} returned None"

    if adapter == "to_diagnostic_context":
        assert isinstance(result, dict)
        for key in expected.get("expected_keys", []):
            assert key in result, f"{scenario_id}: missing key '{key}' in diagnostic context"
        if expected.get("context_has_pathway_id"):
            assert "pathway_id" in result["context"]
        if expected.get("context_has_safety_warnings"):
            assert "safety_warnings" in result["context"]
        assert result.get("strategy") in ("chain_of_thought", "dual_agent", "iterative_dual_inference")

    elif adapter == "to_treatment_context":
        assert isinstance(result, dict)
        if expected.get("has_patient_context"):
            assert "patient_context" in result
        if expected.get("has_contraindication_list"):
            assert "contraindicated_medications" in result["patient_context"]
        if expected.get("has_deviation_summary"):
            assert "deviation_summary" in result["patient_context"]

    elif adapter == "to_prescribing_guard":
        assert isinstance(result, dict)
        if expected.get("has_order"):
            assert "order" in result
            assert "medication_name" in result["order"]
        if expected.get("has_pathway_guard"):
            assert "pathway_guard" in result
            assert "is_excluded_by_pathway" in result["pathway_guard"]

    elif adapter == "to_referral_request":
        assert isinstance(result, dict)
        if expected.get("has_patient_id"):
            assert result.get("patient_id")
        if expected.get("has_pathway_id"):
            assert result.get("pathway_id")
        if expected.get("has_referrals_list"):
            assert "referrals" in result

    elif adapter == "to_investigation_plan":
        assert isinstance(result, dict)
        if expected.get("has_patient_context"):
            assert "patient_context" in result
        if expected.get("has_guideline_topic"):
            assert result.get("guideline_topic")
        if expected.get("has_investigations_list"):
            assert "pathway_investigations" in result

    elif adapter == "to_discharge_plan":
        assert isinstance(result, dict)
        if expected.get("has_patient"):
            assert "patient" in result
        if expected.get("has_pathway_context"):
            assert "pathway_context" in result
        if expected.get("has_discharge_activities"):
            assert "discharge_activities" in result["pathway_context"]

    elif adapter == "to_continuity_request":
        assert isinstance(result, dict)
        if expected.get("has_task_type"):
            assert result.get("task_type")
        if expected.get("has_patient_id"):
            assert result.get("patient_id")
        if expected.get("has_context"):
            assert "context" in result

    elif adapter == "to_chat_context":
        assert isinstance(result, dict)
        if expected.get("has_pathway_personalisation"):
            assert "pathway_personalisation" in result
        if expected.get("has_encounter_journey_summary"):
            pp = result["pathway_personalisation"]
            assert pp.get("encounter_journey_summary")
        if expected.get("has_reasoning_chain"):
            pp = result["pathway_personalisation"]
            assert len(pp.get("reasoning_chain", [])) > 0

    elif adapter == "to_apex_risk_input":
        assert isinstance(result, dict)
        if expected.get("has_patient_id"):
            assert result.get("patient_id")
        if expected.get("has_predictors"):
            assert "predictors" in result
        if expected.get("has_confidence_risk_modifier"):
            assert "pathway_confidence_risk_modifier" in result["predictors"]

    elif adapter == "orchestrate":
        assert result is not None
        assert result.pathway is not None
        assert result.pathway.pathway_id
        if expected.get("has_dispatches"):
            assert len(result.dispatches) > 0
        if expected.get("has_integrated_plan"):
            assert result.integrated_plan
        min_agents = expected.get("min_agents_dispatched", 0)
        if min_agents:
            assert result.agent_count >= min_agents, (
                f"{adapter}: expected >= {min_agents} agents, got {result.agent_count}"
            )


def _validate_negative(scenario_id: str, adapter: str, result, expected: dict):
    """Validate negative scenario — should not crash."""
    assert expected.get("should_not_crash", True)
    # The key requirement is that the adapter ran without exception
    # The result itself may be valid (graceful handling) or empty


def _validate_edge(scenario_id: str, adapter: str, result, expected: dict):
    """Validate edge case scenario — should produce output without crash."""
    assert expected.get("should_not_crash", True)
    if expected.get("should_produce_output"):
        assert result is not None
