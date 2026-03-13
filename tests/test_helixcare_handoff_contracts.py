"""Schema coverage tests for handoff contracts across HelixCare journeys."""

from __future__ import annotations

import os
import sys


def _load_scenarios():
    root = os.path.dirname(os.path.dirname(__file__))
    tools_dir = os.path.join(root, "tools")
    sys.path.insert(0, tools_dir)
    os.chdir(tools_dir)
    from additional_scenarios import ADDITIONAL_SCENARIOS
    from clinical_negative_scenarios import CLINICAL_NEGATIVE_SCENARIOS
    from helixcare_scenarios import SCENARIOS, enrich_scenario_handoff_contracts

    additional = list(ADDITIONAL_SCENARIOS)
    enrich_scenario_handoff_contracts(additional)

    return list(SCENARIOS), additional, list(CLINICAL_NEGATIVE_SCENARIOS)


def test_all_25_journeys_have_explicit_handoff_contracts():
    canonical, additional, _negatives = _load_scenarios()
    combined = canonical + additional
    assert len(canonical) == 10
    assert len(additional) >= 15
    assert len(combined) >= 25

    for scenario in combined:
        for step in scenario.journey_steps:
            policy = step.get("handoff_policy")
            assert isinstance(policy, dict), (
                f"{scenario.name}:{step.get('agent')} missing handoff_policy"
            )
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


def test_transfer_steps_include_receiving_team_ownership():
    canonical, additional, _negatives = _load_scenarios()
    combined = canonical + additional

    transfer_agents = {"bed_manager", "discharge", "followup", "coordinator"}
    for scenario in combined:
        for step in scenario.journey_steps:
            if str(step.get("agent")).lower() not in transfer_agents:
                continue
            params = step.get("params")
            assert isinstance(params, dict)
            transition = params.get("care_transition")
            assert isinstance(transition, dict), (
                f"{scenario.name}:{step.get('agent')} missing care_transition"
            )
            assert transition.get("handover_owner"), (
                f"{scenario.name}:{step.get('agent')} missing handover_owner"
            )
            assert transition.get("receiving_team"), (
                f"{scenario.name}:{step.get('agent')} missing receiving_team"
            )


def test_clinical_negative_library_exists():
    _canonical, _additional, negatives = _load_scenarios()
    assert len(negatives) >= 6
    for scenario in negatives:
        assert scenario.negative_class == "clinical_handoff"
        assert scenario.expected_escalation
        assert scenario.expected_safe_outcome


def test_registration_failure_urgent_override_markers_present():
    _canonical, additional, _negatives = _load_scenarios()
    target_name = "registration_failed_urgent_clinical_override"
    scenario = next(
        (s for s in additional if s.name == target_name),
        None,
    )
    assert scenario is not None

    journey_steps = scenario.journey_steps
    triage_step = next(
        (step for step in journey_steps if step.get("agent") == "triage"),
        None,
    )
    assert triage_step is not None

    params = triage_step.get("params", {})
    assert params.get("clinical_override") is True
    assert params.get("financial_clearance_state") == "pending"
