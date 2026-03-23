"""Integration tests — verify strategy wiring into existing prompt constructors."""

from __future__ import annotations

import pytest

from shared.nexus_common.prompt_strategy import (
    PromptStrategy,
    PromptStrategySelector,
    TaskContext,
    get_strategy_registry,
)
from shared.nexus_common.prompt_strategy.models import (
    StrategySource,
    StrategyTemplate,
    StrategyWhenToUse,
)


# ── Helpers ────────────────────────────────────────────────────────────

def _cot_strategy() -> PromptStrategy:
    """A chain-of-thought strategy for test injection."""
    return PromptStrategy(
        id="cot_test",
        name="CoT Test",
        description="Test CoT",
        strategy_type="reasoning",
        when_to_use=StrategyWhenToUse(),
        template=StrategyTemplate(
            prefix="",
            suffix="",
            system_addendum="STRATEGY-MARKER: Use chain-of-thought reasoning.",
            few_shot_examples=[],
        ),
        parameters={},
        source=StrategySource(),
    )


_SAMPLE_PATIENT_CONTEXT: dict = {
    "patient_profile": {"name": "Test Patient", "age": 55, "sex": "M", "urgency": "high"},
    "medical_history": {"conditions": ["hypertension"]},
    "agent_outputs": {},
}


# ── Backward Compatibility ─────────────────────────────────────────────

class TestBackwardCompatibility:
    """Calling prompt functions without strategy must produce identical output."""

    def test_persona_prompt_no_strategy(self):
        from shared.clinician_avatar.prompts.clinician_persona import build_persona_prompt

        persona = {"name": "Dr. Test", "role": "clinician", "style": "calm", "specialty": "cardiology"}
        result = build_persona_prompt(persona, "calgary_cambridge", "initiating")
        assert "Dr. Test" in result
        assert "cardiology" in result
        # No strategy addendum
        assert "STRATEGY-MARKER" not in result

    def test_imaging_prompt_no_strategy(self):
        from shared.nexus_common.clinical_prompts import imaging_prompt

        sys, usr = imaging_prompt(_SAMPLE_PATIENT_CONTEXT, "chest_xray")
        assert "radiologist" in sys.lower()
        assert "chest_xray" in usr

    def test_lab_prompt_no_strategy(self):
        from shared.nexus_common.clinical_prompts import lab_prompt

        sys, usr = lab_prompt(_SAMPLE_PATIENT_CONTEXT, ["troponin_i", "cbc"])
        assert "laboratory" in sys.lower()
        assert "troponin_i" in usr

    def test_pharmacy_prompt_no_strategy(self):
        from shared.nexus_common.clinical_prompts import pharmacy_prompt

        sys, usr = pharmacy_prompt(_SAMPLE_PATIENT_CONTEXT)
        assert "pharmacist" in sys.lower()

    def test_diagnosis_prompt_no_strategy(self):
        from shared.nexus_common.clinical_prompts import diagnosis_prompt

        sys, usr = diagnosis_prompt(_SAMPLE_PATIENT_CONTEXT)
        assert "clinician" in sys.lower()


# ── Strategy-Enhanced Prompts ──────────────────────────────────────────

class TestStrategyEnhanced:
    """Passing a strategy must add the addendum to prompts."""

    def test_persona_prompt_with_strategy(self):
        from shared.clinician_avatar.prompts.clinician_persona import build_persona_prompt

        persona = {"name": "Dr. Test", "role": "clinician", "style": "calm", "specialty": "cardiology"}
        result = build_persona_prompt(persona, "calgary_cambridge", "initiating", strategy=_cot_strategy())
        assert "Dr. Test" in result
        assert "STRATEGY-MARKER: Use chain-of-thought reasoning." in result

    def test_imaging_prompt_with_strategy(self):
        from shared.nexus_common.clinical_prompts import imaging_prompt

        sys, usr = imaging_prompt(_SAMPLE_PATIENT_CONTEXT, "chest_xray", strategy=_cot_strategy())
        assert "STRATEGY-MARKER: Use chain-of-thought reasoning." in sys
        assert "radiologist" in sys.lower()

    def test_lab_prompt_with_strategy(self):
        from shared.nexus_common.clinical_prompts import lab_prompt

        sys, usr = lab_prompt(_SAMPLE_PATIENT_CONTEXT, ["cbc"], strategy=_cot_strategy())
        assert "STRATEGY-MARKER" in sys

    def test_pharmacy_prompt_with_strategy(self):
        from shared.nexus_common.clinical_prompts import pharmacy_prompt

        sys, usr = pharmacy_prompt(_SAMPLE_PATIENT_CONTEXT, strategy=_cot_strategy())
        assert "STRATEGY-MARKER" in sys

    def test_diagnosis_prompt_with_strategy(self):
        from shared.nexus_common.clinical_prompts import diagnosis_prompt

        sys, usr = diagnosis_prompt(_SAMPLE_PATIENT_CONTEXT, strategy=_cot_strategy())
        assert "STRATEGY-MARKER" in sys


# ── End-to-End: Registry → Selector → Applicator ──────────────────────

class TestEndToEnd:
    """Full pipeline: load real registry, select a strategy, apply to a prompt."""

    def test_full_pipeline_diagnosis(self):
        from shared.nexus_common.clinical_prompts import diagnosis_prompt

        registry = get_strategy_registry()
        selector = PromptStrategySelector(registry)

        ctx = TaskContext(task_type="diagnosis", complexity="medium", urgency="high", domain="clinical")
        strategy = selector.select(ctx)
        assert strategy is not None, "Selector should find a strategy for diagnosis"

        sys, usr = diagnosis_prompt(_SAMPLE_PATIENT_CONTEXT, strategy=strategy)
        # The selected strategy's addendum should be in the system prompt
        assert strategy.template.system_addendum in sys

    def test_full_pipeline_imaging(self):
        from shared.nexus_common.clinical_prompts import imaging_prompt

        registry = get_strategy_registry()
        selector = PromptStrategySelector(registry)

        ctx = TaskContext(task_type="imaging", complexity="low", urgency="medium", domain="imaging")
        strategy = selector.select(ctx)
        assert strategy is not None

        sys, usr = imaging_prompt(_SAMPLE_PATIENT_CONTEXT, "chest_xray", strategy=strategy)
        assert strategy.template.system_addendum in sys

    def test_full_pipeline_avatar_conversation(self):
        from shared.clinician_avatar.prompts.clinician_persona import build_persona_prompt

        registry = get_strategy_registry()
        selector = PromptStrategySelector(registry)

        ctx = TaskContext(task_type="avatar_conversation", complexity="medium", urgency="medium", domain="clinical")
        strategy = selector.select(ctx)
        assert strategy is not None

        persona = {"name": "Dr. Pipeline", "role": "clinician", "style": "calm", "specialty": "medicine"}
        result = build_persona_prompt(persona, "calgary_cambridge", "initiating", strategy=strategy)
        assert strategy.template.system_addendum in result

    def test_no_match_falls_back_gracefully(self):
        from shared.nexus_common.clinical_prompts import diagnosis_prompt

        registry = get_strategy_registry()
        selector = PromptStrategySelector(registry)

        ctx = TaskContext(task_type="nonexistent", complexity="low", urgency="low", domain="nonexistent")
        strategy = selector.select(ctx)
        assert strategy is None

        # Passing None should produce unchanged prompts
        sys, usr = diagnosis_prompt(_SAMPLE_PATIENT_CONTEXT, strategy=strategy)
        assert "clinician" in sys.lower()
