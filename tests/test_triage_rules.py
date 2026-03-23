"""Tests for the consolidated triage rules module."""

from __future__ import annotations

from shared.nexus_common.triage_rules import (
    _FALLBACK_RULES,
    _apply_rules,
    evaluate_triage,
    evaluate_triage_from_task,
)

# ── Direct rule evaluation ───────────────────────────────────────────────


class TestEvaluateTriage:
    def test_chest_pain_esi2(self):
        assert evaluate_triage("Severe chest pain") == "ESI-2"

    def test_shortness_of_breath_esi2(self):
        assert evaluate_triage("acute shortness of breath") == "ESI-2"

    def test_low_spo2_esi2(self):
        assert evaluate_triage("cough", {"spo2": 88}) == "ESI-2"

    def test_high_temp_esi2(self):
        assert evaluate_triage("headache", {"temp_c": 39.5}) == "ESI-2"

    def test_confusion_esi2(self):
        assert evaluate_triage("sudden confusion and disorientation") == "ESI-2"

    def test_laceration_esi4(self):
        assert evaluate_triage("minor laceration on forearm") == "ESI-4"

    def test_default_esi3(self):
        assert evaluate_triage("mild headache") == "ESI-3"

    def test_empty_complaint_default(self):
        assert evaluate_triage("") == "ESI-3"

    def test_normal_vitals_no_escalation(self):
        assert evaluate_triage("knee pain", {"spo2": 99, "temp_c": 36.6}) == "ESI-3"

    def test_borderline_spo2_90_no_escalation(self):
        # spo2 == 90 should NOT trigger (rule is < 90)
        assert evaluate_triage("cough", {"spo2": 90}) == "ESI-3"

    def test_borderline_temp_39_triggers(self):
        # temp_c >= 39.0 should trigger
        assert evaluate_triage("headache", {"temp_c": 39.0}) == "ESI-2"

    def test_missing_vitals_graceful(self):
        assert evaluate_triage("chest tightness", {}) == "ESI-2"

    def test_invalid_vitals_type_graceful(self):
        assert evaluate_triage("headache", {"spo2": "not_a_number"}) == "ESI-3"

    def test_case_insensitive(self):
        assert evaluate_triage("CHEST PAIN") == "ESI-2"
        assert evaluate_triage("Shortness Of Breath") == "ESI-2"


# ── Task-based evaluation ────────────────────────────────────────────────


class TestEvaluateTriageFromTask:
    def test_task_with_chief_complaint(self):
        task = {"chief_complaint": "chest pain", "vitals": {"spo2": 95}}
        assert evaluate_triage_from_task(task) == "ESI-2"

    def test_task_with_inputs_chief_complaint(self):
        task = {"inputs": {"chief_complaint": "laceration on hand"}}
        assert evaluate_triage_from_task(task) == "ESI-4"

    def test_task_with_vitals(self):
        task = {"chief_complaint": "headache", "vitals": {"spo2": 85, "temp_c": 37.0}}
        assert evaluate_triage_from_task(task) == "ESI-2"

    def test_task_empty(self):
        assert evaluate_triage_from_task({}) == "ESI-3"

    def test_task_no_vitals_key(self):
        task = {"chief_complaint": "mild nausea"}
        assert evaluate_triage_from_task(task) == "ESI-3"


# ── Fallback rules ───────────────────────────────────────────────────────


class TestFallbackRules:
    def test_fallback_produces_same_results(self):
        cases = [
            ("chest pain", {}, "ESI-2"),
            ("shortness of breath", {}, "ESI-2"),
            ("cough", {"spo2": 88}, "ESI-2"),
            ("headache", {"temp_c": 39.5}, "ESI-2"),
            ("confusion", {}, "ESI-2"),
            ("laceration", {}, "ESI-4"),
            ("headache", {}, "ESI-3"),
        ]
        for complaint, vitals, expected in cases:
            result = _apply_rules(_FALLBACK_RULES, complaint, vitals)
            assert result == expected, (
                f"Fallback mismatch for '{complaint}': {result} != {expected}"
            )
