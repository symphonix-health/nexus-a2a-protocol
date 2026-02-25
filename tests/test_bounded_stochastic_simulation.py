"""Tests for bounded stochastic scenario branch selection."""

from __future__ import annotations

import random

from tools.helixcare_scenarios import _choose_simulation_branch
from shared.nexus_common.clinical_handoff_rules import apply_nhs_guardrails
from tools.clinical_negative_scenarios import CLINICAL_NEGATIVE_SCENARIOS


def _sequence(seed: int, variance_band: str, n: int = 120) -> list[str]:
    rng = random.Random(seed)
    profile = {
        "seed": seed,
        "variance_band": variance_band,
        "allowed_branches": ["nominal", "handoff_delay", "context_gap"],
    }
    return [_choose_simulation_branch(rng=rng, profile=profile) for _ in range(n)]


def test_same_seed_replays_identical_sequence():
    a = _sequence(12345, "medium", n=80)
    b = _sequence(12345, "medium", n=80)
    assert a == b


def test_low_variance_is_mostly_nominal():
    seq = _sequence(999, "low", n=200)
    nominal_ratio = sum(1 for s in seq if s == "nominal") / len(seq)
    assert nominal_ratio >= 0.75


def test_high_variance_has_more_non_nominal_than_low():
    low = _sequence(42, "low", n=300)
    high = _sequence(42, "high", n=300)
    low_non_nominal = sum(1 for s in low if s != "nominal")
    high_non_nominal = sum(1 for s in high if s != "nominal")
    assert high_non_nominal > low_non_nominal


def test_safety_invariant_holds_under_monte_carlo_for_negative_discharge():
    scenario = next(s for s in CLINICAL_NEGATIVE_SCENARIOS if s.name == "negative_missing_discharge_summary")
    step = scenario.journey_steps[0]
    policy = step.get("handoff_policy", {})
    clinical_context = {"patient_profile": dict(scenario.patient_profile), "handover": {}}

    rng = random.Random(2026)
    profile = {"variance_band": "high", "allowed_branches": ["nominal", "handoff_delay", "context_gap"]}
    # Safety invariant: regardless of stochastic branch, guardrails block unsafe discharge.
    for _ in range(200):
        _choose_simulation_branch(rng=rng, profile=profile)
        result = apply_nhs_guardrails(step, policy, clinical_context)
        assert result.allowed is False
        assert result.reason_code in {"missing_handover_contract", "unsafe_discharge_prevented"}
