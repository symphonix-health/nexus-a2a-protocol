"""Coverage tests for expanded representative HelixCare journeys."""

from __future__ import annotations

import os
import sys


def _load_representative():
    root = os.path.dirname(os.path.dirname(__file__))
    tools_dir = os.path.join(root, "tools")
    sys.path.insert(0, tools_dir)
    previous_cwd = os.getcwd()
    try:
        os.chdir(tools_dir)
        from representative_scenarios import REPRESENTATIVE_SCENARIOS

        return list(REPRESENTATIVE_SCENARIOS)
    finally:
        os.chdir(previous_cwd)


def test_representative_pack_size_and_balance():
    scenarios = _load_representative()
    negatives = [s for s in scenarios if s.negative_class == "clinical_handoff"]
    positives = [s for s in scenarios if s.negative_class != "clinical_handoff"]

    assert len(scenarios) >= 70
    assert len(positives) >= 50
    assert len(negatives) >= 18


def test_representative_axes_cover_realistic_dimensions():
    scenarios = _load_representative()
    contexts: set[str] = set()
    risk_bands: set[str] = set()
    care_settings: set[str] = set()
    communication_profiles: set[str] = set()
    classes: set[str] = set()

    for scenario in scenarios:
        profile = dict(getattr(scenario, "simulation_profile", {}) or {})
        axes = dict(profile.get("representative_axes", {}) or {})
        contexts.add(str(axes.get("operational_context", "")))
        risk_bands.add(str(axes.get("risk_band", "")))
        care_settings.add(str(axes.get("care_setting", "")))
        communication_profiles.add(str(axes.get("communication_profile", "")))
        classes.add(str(axes.get("scenario_class", "")))

    assert {"weekday_in_hours", "weekday_overnight", "weekend_day", "winter_pressure"} <= contexts
    assert {"low", "medium", "high"} <= risk_bands
    assert {
        "ed_to_inpatient",
        "inpatient_to_discharge_to_assess",
        "community_to_primary",
        "mental_health_crisis_to_community",
        "discharge_to_community_followup",
    } <= care_settings
    assert {"standard", "interpreter_urdu", "bsl_interpreter", "cognitive_support"} <= communication_profiles
    assert {"positive", "clinical_negative"} <= classes


def test_representative_negative_scenarios_define_expected_safe_outcomes():
    scenarios = _load_representative()
    negatives = [s for s in scenarios if s.negative_class == "clinical_handoff"]
    for scenario in negatives:
        assert scenario.expected_escalation
        assert scenario.expected_safe_outcome
        assert scenario.simulation_profile.get("representative_axes", {}).get("failure_mode")


def test_representative_scenarios_have_explicit_handoff_contracts():
    scenarios = _load_representative()
    for scenario in scenarios:
        for step in scenario.journey_steps:
            policy = step.get("handoff_policy")
            assert isinstance(policy, dict), f"{scenario.name}:{step.get('agent')} missing handoff_policy"
            for required_key in (
                "criticality",
                "required_handover_fields",
                "escalation_path",
                "max_wait_seconds",
                "fallback_mode",
            ):
                assert required_key in policy, (
                    f"{scenario.name}:{step.get('agent')} missing policy field {required_key}"
                )
