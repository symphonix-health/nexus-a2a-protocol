from __future__ import annotations

from tools.traffic_generator import ScenarioRuntimeIsolation, scenario_runtime_key


def test_scenario_runtime_key_is_stable_for_equivalent_payloads() -> None:
    a = {
        "scenario_id": "scn-1",
        "input_payload": {"task": {"b": 2, "a": 1}},
    }
    b = {
        "scenario_id": "scn-1",
        "input_payload": {"task": {"a": 1, "b": 2}},
    }
    assert scenario_runtime_key(a) == scenario_runtime_key(b)


def test_runtime_isolation_quarantines_after_threshold() -> None:
    isolation = ScenarioRuntimeIsolation(error_threshold=2)
    key = "k1"
    assert isolation.is_quarantined(key) is False
    assert isolation.observe(key, {"status": "error"}) is False
    assert isolation.observe(key, {"status": "error"}) is True
    assert isolation.is_quarantined(key) is True


def test_runtime_isolation_resets_error_streak_on_non_error_outcome() -> None:
    isolation = ScenarioRuntimeIsolation(error_threshold=2)
    key = "k2"
    assert isolation.observe(key, {"status": "error"}) is False
    assert isolation.observe(key, {"status": "pass"}) is False
    assert isolation.observe(key, {"status": "error"}) is False
    assert isolation.is_quarantined(key) is False


def test_runtime_isolation_clamps_threshold_to_positive_value() -> None:
    isolation = ScenarioRuntimeIsolation(error_threshold=0)
    key = "k3"
    assert isolation.observe(key, {"status": "error"}) is True
    assert isolation.is_quarantined(key) is True
