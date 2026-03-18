"""L5 Unit Tests — Safety guardrails."""

import pytest
from clinical_pathways.engine.models import ModificationType
from clinical_pathways.engine.safety import SafetyGuardrails

from .conftest import make_patient_context


class TestSafetyGuardrails:
    def setup_method(self):
        self.safety = SafetyGuardrails()

    def test_critical_hyperkalaemia(self):
        ctx = make_patient_context(observations=[{"code": "potassium", "value": 6.5}])
        mods = self.safety._check_critical_lab_values(ctx)
        assert len(mods) >= 1
        assert any("Hyperkalaemia" in m.description for m in mods)

    def test_critical_hypokalaemia(self):
        ctx = make_patient_context(observations=[{"code": "potassium", "value": 2.5}])
        mods = self.safety._check_critical_lab_values(ctx)
        assert len(mods) >= 1
        assert any("Hypokalaemia" in m.description for m in mods)

    def test_normal_potassium_no_flag(self):
        ctx = make_patient_context(observations=[{"code": "potassium", "value": 4.2}])
        mods = self.safety._check_critical_lab_values(ctx)
        pot_mods = [m for m in mods if "potassium" in str(m.context_factors)]
        assert len(pot_mods) == 0

    def test_severe_renal_failure(self):
        ctx = make_patient_context(observations=[{"code": "egfr", "value": 10.0}])
        mods = self.safety._check_critical_lab_values(ctx)
        assert any("renal failure" in m.description.lower() for m in mods)

    def test_elevated_lactate(self):
        ctx = make_patient_context(observations=[{"code": "lactate", "value": 5.0}])
        mods = self.safety._check_critical_lab_values(ctx)
        assert any("lactate" in str(m.context_factors) for m in mods)

    def test_triple_whammy_interaction(self):
        ctx = make_patient_context(medications=[
            {"code": "ramipril"},
            {"code": "spironolactone"},
            {"code": "ibuprofen"},
        ])
        mods = self.safety._check_drug_interactions(ctx)
        assert len(mods) >= 1
        assert any("Triple whammy" in m.description for m in mods)

    def test_no_triple_whammy_without_nsaid(self):
        ctx = make_patient_context(medications=[
            {"code": "ramipril"},
            {"code": "spironolactone"},
        ])
        mods = self.safety._check_drug_interactions(ctx)
        triple = [m for m in mods if "Triple whammy" in m.description]
        assert len(triple) == 0

    def test_metformin_renal_impairment(self):
        ctx = make_patient_context(
            medications=[{"code": "metformin"}],
            observations=[{"code": "egfr", "value": 20.0}],
        )
        mods = self.safety._check_drug_interactions(ctx)
        assert any("metformin" in m.description.lower() for m in mods)

    def test_no_labs_no_flags(self):
        ctx = make_patient_context()
        mods = self.safety._check_critical_lab_values(ctx)
        assert len(mods) == 0
