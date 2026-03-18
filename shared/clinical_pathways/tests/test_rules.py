"""L5 Unit Tests — Personalisation rules."""

import pytest
from clinical_pathways.engine.models import ModificationType
from clinical_pathways.engine.rules import get_all_rules

from .conftest import make_patient_context


class TestCrossPathwayRules:
    def test_polypharmacy_rule_triggers(self):
        ctx = make_patient_context(medications=[{"code": f"med{i}"} for i in range(12)])
        rules = get_all_rules()
        poly_rule = next(r for name, r in rules if name == "polypharmacy_medication_review")
        mods = poly_rule.evaluate(ctx, "any-pathway")
        assert len(mods) >= 1
        assert mods[0].modification_type == ModificationType.SEQUENCE_CHANGED

    def test_polypharmacy_rule_does_not_trigger(self):
        ctx = make_patient_context(medications=[{"code": "med1"}])
        rules = get_all_rules()
        poly_rule = next(r for name, r in rules if name == "polypharmacy_medication_review")
        mods = poly_rule.evaluate(ctx, "any-pathway")
        assert len(mods) == 0

    def test_frailty_rule_moderate(self):
        ctx = make_patient_context(frailty_score="moderate")
        rules = get_all_rules()
        frailty_rule = next(r for name, r in rules if name == "frailty_intensity_adjustment")
        mods = frailty_rule.evaluate(ctx, "any-pathway")
        assert len(mods) >= 1
        assert mods[0].modification_type == ModificationType.FOLLOW_UP_ADAPTED

    def test_frailty_rule_severe(self):
        ctx = make_patient_context(frailty_score="severe")
        rules = get_all_rules()
        frailty_rule = next(r for name, r in rules if name == "frailty_intensity_adjustment")
        mods = frailty_rule.evaluate(ctx, "any-pathway")
        assert len(mods) >= 2
        types = {m.modification_type for m in mods}
        assert ModificationType.INTENSITY_REDUCED in types

    def test_frailty_rule_fit_no_trigger(self):
        ctx = make_patient_context(frailty_score="fit")
        rules = get_all_rules()
        frailty_rule = next(r for name, r in rules if name == "frailty_intensity_adjustment")
        mods = frailty_rule.evaluate(ctx, "any-pathway")
        assert len(mods) == 0

    def test_language_barrier_rule(self):
        ctx = make_patient_context(social_history={"interpreter_needed": True})
        rules = get_all_rules()
        lang_rule = next(r for name, r in rules if name == "language_barrier_adaptation")
        mods = lang_rule.evaluate(ctx, "any-pathway")
        assert len(mods) == 1
        assert mods[0].modification_type == ModificationType.ACTIVITY_ADDED

    def test_transport_barrier_rule(self):
        ctx = make_patient_context(social_history={"transport_access": "poor"})
        rules = get_all_rules()
        transport_rule = next(r for name, r in rules if name == "transport_barrier_followup")
        mods = transport_rule.evaluate(ctx, "any-pathway")
        assert len(mods) == 1


class TestHeartFailureRules:
    def test_hf_ckd_renal_safe(self):
        ctx = make_patient_context(
            conditions=[{"code": "heart_failure"}, {"code": "ckd_stage_3"}],
            observations=[{"code": "egfr", "value": 35.0}],
        )
        rules = get_all_rules()
        ckd_rule = next(r for name, r in rules if name == "hf_ckd_renal_safe")
        mods = ckd_rule.evaluate(ctx, "nice-ng106-heart-failure")
        assert len(mods) >= 2

    def test_hf_ckd_severe_contraindication(self):
        ctx = make_patient_context(
            conditions=[{"code": "heart_failure"}, {"code": "ckd"}],
            observations=[{"code": "egfr", "value": 20.0}],
        )
        rules = get_all_rules()
        ckd_rule = next(r for name, r in rules if name == "hf_ckd_renal_safe")
        mods = ckd_rule.evaluate(ctx, "nice-ng106-heart-failure")
        assert any(m.modification_type == ModificationType.CONTRAINDICATION_FLAGGED for m in mods)

    def test_hf_ckd_no_ckd_no_trigger(self):
        ctx = make_patient_context(
            conditions=[{"code": "heart_failure"}],
            observations=[{"code": "egfr", "value": 75.0}],
        )
        rules = get_all_rules()
        ckd_rule = next(r for name, r in rules if name == "hf_ckd_renal_safe")
        mods = ckd_rule.evaluate(ctx, "nice-ng106-heart-failure")
        assert len(mods) == 0


class TestSepsisRules:
    def test_sepsis_penicillin_allergy(self):
        ctx = make_patient_context(
            allergies=[{"substance": "penicillin"}],
        )
        rules = get_all_rules()
        pen_rule = next(r for name, r in rules if name == "sepsis_penicillin_allergy")
        mods = pen_rule.evaluate(ctx, "nice-ng51-sepsis")
        assert len(mods) == 1
        assert mods[0].modification_type == ModificationType.CONTRAINDICATION_FLAGGED

    def test_sepsis_immunocompromised(self):
        ctx = make_patient_context(
            conditions=[{"code": "immunocompromised"}],
        )
        rules = get_all_rules()
        immuno_rule = next(r for name, r in rules if name == "sepsis_immunocompromised")
        mods = immuno_rule.evaluate(ctx, "nice-ng51-sepsis")
        assert len(mods) >= 2

    def test_sepsis_hf_cautious_fluids(self):
        ctx = make_patient_context(
            conditions=[{"code": "heart_failure"}],
        )
        rules = get_all_rules()
        hf_rule = next(r for name, r in rules if name == "sepsis_hf_cautious_fluids")
        mods = hf_rule.evaluate(ctx, "nice-ng51-sepsis")
        assert len(mods) == 1
        assert mods[0].modification_type == ModificationType.SAFETY_OVERRIDE


class TestDiabetesRules:
    def test_dm2_renal_impairment(self):
        ctx = make_patient_context(
            observations=[{"code": "egfr", "value": 22.0}],
        )
        rules = get_all_rules()
        renal_rule = next(r for name, r in rules if name == "dm2_renal_impairment")
        mods = renal_rule.evaluate(ctx, "nice-ng28-diabetes-type2")
        assert len(mods) >= 1
        assert any(m.modification_type == ModificationType.CONTRAINDICATION_FLAGGED for m in mods)

    def test_dm2_foot_ulcer(self):
        ctx = make_patient_context(
            conditions=[{"code": "diabetic_foot_ulcer"}],
            observations=[{"code": "hba1c", "value": 82.0}],
        )
        rules = get_all_rules()
        foot_rule = next(r for name, r in rules if name == "dm2_foot_ulcer_mdl")
        mods = foot_rule.evaluate(ctx, "nice-ng28-diabetes-type2")
        assert len(mods) >= 2


class TestMaternalRules:
    def test_anc_advanced_age(self):
        ctx = make_patient_context(age=42, gender="female")
        rules = get_all_rules()
        age_rule = next(r for name, r in rules if name == "anc_advanced_maternal_age")
        mods = age_rule.evaluate(ctx, "who-maternal-anc")
        assert len(mods) == 1
        assert mods[0].modification_type == ModificationType.INTENSITY_INCREASED

    def test_anc_pre_eclampsia_history(self):
        ctx = make_patient_context(
            age=32,
            gender="female",
            conditions=[{"code": "pre_eclampsia"}],
        )
        rules = get_all_rules()
        pe_rule = next(r for name, r in rules if name == "anc_pre_eclampsia_history")
        mods = pe_rule.evaluate(ctx, "who-maternal-anc")
        assert len(mods) >= 2
