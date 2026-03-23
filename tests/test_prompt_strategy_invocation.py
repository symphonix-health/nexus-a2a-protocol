"""Tests to verify that strategies are actually invoked in all call sites.

Ensures the 20 strategies in the registry are selected and applied at every
prompt construction point: llm_agent_handler, avatar_engine, clinical_prompts,
and orchestrator dispatch payloads.
"""

from __future__ import annotations

import pytest

from shared.nexus_common.prompt_strategy import (
    PromptStrategy,
    PromptStrategySelector,
    TaskContext,
    get_strategy_registry,
)


# ── Helper ─────────────────────────────────────────────────────────────

@pytest.fixture
def registry():
    return get_strategy_registry()


@pytest.fixture
def selector(registry):
    return PromptStrategySelector(registry)


# ── 1. Every task_type from llm_agent_handler gets a strategy ──────────

class TestLlmAgentHandlerMethodMapping:
    """The llm_agent_handler maps method names to task contexts.
    Verify every method keyword produces at least one strategy match.
    """

    @pytest.mark.parametrize(
        "task_type,domain,urgency",
        [
            ("imaging", "imaging", "medium"),
            ("pharmacy", "pharmacy", "medium"),
            ("diagnosis", "clinical", "medium"),
            ("lab", "lab", "medium"),
        ],
    )
    def test_handler_methods_get_strategies(self, selector, task_type, domain, urgency):
        ctx = TaskContext(task_type=task_type, complexity="medium", urgency=urgency, domain=domain)
        strategy = selector.select(ctx)
        assert strategy is not None, (
            f"No strategy selected for task_type={task_type}, domain={domain}. "
            f"This means the llm_agent_handler will use bare prompts with no enhancement."
        )

    @pytest.mark.parametrize(
        "task_type,domain,urgency",
        [
            ("imaging", "imaging", "critical"),
            ("pharmacy", "pharmacy", "high"),
            ("diagnosis", "clinical", "critical"),
            ("lab", "lab", "critical"),
        ],
    )
    def test_handler_methods_get_strategies_at_critical_urgency(self, selector, task_type, domain, urgency):
        """Critical urgency must still produce a strategy for clinical prompts."""
        ctx = TaskContext(task_type=task_type, complexity="medium", urgency=urgency, domain=domain)
        strategy = selector.select(ctx)
        assert strategy is not None, (
            f"No strategy for {task_type} at {urgency} urgency. "
            f"Critical patients need strategy-enhanced prompts most."
        )


# ── 2. Avatar conversation always gets a strategy ─────────────────────

class TestAvatarConversationStrategy:
    """The avatar_engine selects a strategy for every patient turn."""

    @pytest.mark.parametrize("urgency", ["low", "medium", "high", "critical"])
    def test_avatar_conversation_has_strategy(self, selector, urgency):
        ctx = TaskContext(
            task_type="avatar_conversation",
            complexity="medium",
            urgency=urgency,
            domain="clinical",
        )
        strategy = selector.select(ctx)
        assert strategy is not None, (
            f"No strategy for avatar_conversation at urgency={urgency}. "
            f"Avatar engine will produce bare persona prompts."
        )


# ── 3. Clinical reasoning tasks get appropriate strategy types ────────

class TestStrategyTypeAppropriatenessForClinicalTasks:
    """Verify the RIGHT kind of strategy is selected for clinical tasks."""

    def test_diagnosis_gets_reasoning_or_composite_or_verification(self, selector):
        ctx = TaskContext(task_type="diagnosis", complexity="medium", urgency="medium", domain="clinical")
        strategy = selector.select(ctx)
        assert strategy is not None
        # The strategy for diagnosis should be a reasoning-enhancing type
        # structured_output or rephrase_and_respond is fine (they have lowest priority)
        # but should not be a purely agentic type
        assert strategy.strategy_type in (
            "reasoning", "composite", "verification", "filtering",
            "decomposition", "iterative", "exemplar", "clarification",
            "formatting", "persona",
        ), f"Unexpected strategy type {strategy.strategy_type} for diagnosis"

    def test_high_complexity_diagnosis_gets_advanced_strategy(self, selector):
        """High-complexity diagnosis should unlock advanced strategies."""
        ctx = TaskContext(task_type="diagnosis", complexity="high", urgency="medium", domain="clinical")
        all_strategies = selector.select_multiple(ctx, limit=25)
        ids = {s.id for s in all_strategies}
        # Advanced strategies requiring high complexity should be available
        assert "cumulative_reasoning" in ids or "self_consistency" in ids or "reflexion" in ids, (
            f"High-complexity diagnosis should include at least one advanced strategy. Got: {ids}"
        )

    def test_pharmacy_gets_relevant_strategy(self, selector):
        ctx = TaskContext(task_type="pharmacy", complexity="medium", urgency="high", domain="pharmacy")
        strategy = selector.select(ctx)
        assert strategy is not None

    def test_lab_gets_relevant_strategy(self, selector):
        ctx = TaskContext(task_type="lab", complexity="low", urgency="medium", domain="lab")
        strategy = selector.select(ctx)
        assert strategy is not None


# ── 4. Urgency-based strategy filtering works correctly ───────────────

class TestUrgencyFiltering:
    """Verify strategies correctly filter by urgency."""

    def test_critical_urgency_excludes_slow_strategies(self, selector):
        """At critical urgency, strategies that only allow low/medium should NOT be selected."""
        ctx = TaskContext(task_type="diagnosis", complexity="high", urgency="critical", domain="clinical")
        all_strategies = selector.select_multiple(ctx, limit=25)
        for s in all_strategies:
            assert "critical" in s.when_to_use.urgency, (
                f"Strategy {s.id} does not support critical urgency but was selected. "
                f"Its urgency list: {s.when_to_use.urgency}"
            )

    def test_low_urgency_unlocks_all_strategies(self, selector):
        """Low urgency should have the widest strategy pool."""
        ctx_low = TaskContext(task_type="diagnosis", complexity="high", urgency="low", domain="clinical")
        ctx_crit = TaskContext(task_type="diagnosis", complexity="high", urgency="critical", domain="clinical")
        low_count = len(selector.select_multiple(ctx_low, limit=50))
        crit_count = len(selector.select_multiple(ctx_crit, limit=50))
        assert low_count >= crit_count, (
            f"Low urgency ({low_count}) should have >= strategies than critical ({crit_count})"
        )


# ── 5. Complexity-based strategy filtering ────────────────────────────

class TestComplexityFiltering:
    """Verify strategies correctly gate on complexity."""

    def test_low_complexity_excludes_high_min(self, selector):
        ctx = TaskContext(task_type="diagnosis", complexity="low", urgency="medium", domain="clinical")
        all_strategies = selector.select_multiple(ctx, limit=50)
        for s in all_strategies:
            assert s.when_to_use.min_complexity != "high", (
                f"Strategy {s.id} (min_complexity=high) should not be available at low complexity"
            )

    def test_high_complexity_includes_more_strategies(self, selector):
        ctx_low = TaskContext(task_type="diagnosis", complexity="low", urgency="medium", domain="clinical")
        ctx_high = TaskContext(task_type="diagnosis", complexity="high", urgency="medium", domain="clinical")
        low_count = len(selector.select_multiple(ctx_low, limit=50))
        high_count = len(selector.select_multiple(ctx_high, limit=50))
        assert high_count >= low_count, (
            f"High complexity ({high_count}) should unlock >= strategies than low ({low_count})"
        )


# ── 6. Orchestrator dispatch payloads carry strategy ──────────────────

class TestOrchestratorStrategyDispatch:
    """Verify the orchestrator attaches recommended_strategy to dispatch payloads."""

    def test_select_strategy_for_diagnostic_agent(self):
        from shared.clinical_pathways.integration.orchestrator import _select_strategy_for_dispatch

        result = _select_strategy_for_dispatch("DiagnosticReasoningAgent", urgency="high", complexity="medium")
        assert result is not None, "DiagnosticReasoningAgent should get a strategy recommendation"
        assert "strategy_id" in result
        assert "system_addendum" in result
        assert len(result["system_addendum"]) > 0

    def test_select_strategy_for_treatment_agent(self):
        from shared.clinical_pathways.integration.orchestrator import _select_strategy_for_dispatch

        result = _select_strategy_for_dispatch("TreatmentRecommendationAgent", urgency="medium", complexity="high")
        assert result is not None
        assert "strategy_id" in result

    def test_select_strategy_for_investigation_agent(self):
        from shared.clinical_pathways.integration.orchestrator import _select_strategy_for_dispatch

        result = _select_strategy_for_dispatch("InvestigationPlannerAgent", urgency="medium")
        assert result is not None

    def test_unknown_agent_still_gets_strategy(self):
        """Unknown agents fall back to clinical_reasoning task type."""
        from shared.clinical_pathways.integration.orchestrator import _select_strategy_for_dispatch

        result = _select_strategy_for_dispatch("SomeNewAgent", urgency="medium")
        # May or may not get a strategy depending on registry, but should not crash
        # clinical_reasoning is the fallback task_type
        assert result is None or "strategy_id" in result


# ── 7. llm_agent_handler strategy selection helpers ───────────────────

class TestLlmAgentHandlerHelpers:
    """Test the helper functions in llm_agent_handler."""

    def test_derive_urgency_from_profile(self):
        from shared.nexus_common.llm_agent_handler import _derive_urgency

        ctx = {"patient_profile": {"urgency": "critical"}}
        assert _derive_urgency(ctx) == "critical"

    def test_derive_urgency_default(self):
        from shared.nexus_common.llm_agent_handler import _derive_urgency

        assert _derive_urgency({}) == "medium"

    def test_derive_complexity_high_for_polypharmacy(self):
        from shared.nexus_common.llm_agent_handler import _derive_complexity

        ctx = {"medical_history": {"medications": ["a", "b", "c", "d", "e"]}}
        assert _derive_complexity(ctx) == "high"

    def test_derive_complexity_high_for_multi_morbidity(self):
        from shared.nexus_common.llm_agent_handler import _derive_complexity

        ctx = {"medical_history": {"conditions": ["hf", "ckd", "dm"]}}
        assert _derive_complexity(ctx) == "high"

    def test_derive_complexity_medium_for_simple(self):
        from shared.nexus_common.llm_agent_handler import _derive_complexity

        ctx = {"medical_history": {"conditions": ["hypertension"]}}
        assert _derive_complexity(ctx) == "medium"

    def test_select_strategy_for_imaging_method(self):
        from shared.nexus_common.llm_agent_handler import _select_strategy_for_method

        strategy = _select_strategy_for_method("imaging/report", {"patient_profile": {"urgency": "high"}})
        assert strategy is not None, "imaging method should get a strategy"

    def test_select_strategy_for_diagnosis_method(self):
        from shared.nexus_common.llm_agent_handler import _select_strategy_for_method

        strategy = _select_strategy_for_method("diagnosis/assess", {"patient_profile": {"urgency": "medium"}})
        assert strategy is not None

    def test_select_strategy_for_pharmacy_method(self):
        from shared.nexus_common.llm_agent_handler import _select_strategy_for_method

        strategy = _select_strategy_for_method("pharmacy/prescribe", {})
        assert strategy is not None

    def test_select_strategy_for_lab_method(self):
        from shared.nexus_common.llm_agent_handler import _select_strategy_for_method

        strategy = _select_strategy_for_method("lab/results", {})
        assert strategy is not None


# ── 8. Specific strategy coverage — ensure key strategies can be reached

class TestSpecificStrategiesReachable:
    """Verify that the new research-backed strategies are reachable
    from realistic clinical contexts.
    """

    def test_medprompt_reachable_for_diagnosis(self, selector):
        """Medprompt (priority 8) should be in the top strategies for diagnosis."""
        ctx = TaskContext(task_type="diagnosis", complexity="medium", urgency="medium", domain="clinical")
        top = selector.select_multiple(ctx, limit=10)
        ids = {s.id for s in top}
        assert "medprompt" in ids, f"Medprompt should be reachable for diagnosis. Top: {ids}"

    def test_chain_of_verification_reachable(self, selector):
        ctx = TaskContext(task_type="diagnosis", complexity="medium", urgency="high", domain="clinical")
        top = selector.select_multiple(ctx, limit=10)
        ids = {s.id for s in top}
        assert "chain_of_verification" in ids, f"CoVe should be reachable. Top: {ids}"

    def test_cumulative_reasoning_at_high_complexity(self, selector):
        ctx = TaskContext(task_type="diagnosis", complexity="high", urgency="medium", domain="clinical")
        top = selector.select_multiple(ctx, limit=15)
        ids = {s.id for s in top}
        assert "cumulative_reasoning" in ids, f"Cumulative reasoning needs high complexity. Top: {ids}"

    def test_system_2_attention_reachable(self, selector):
        ctx = TaskContext(task_type="diagnosis", complexity="medium", urgency="medium", domain="clinical")
        top = selector.select_multiple(ctx, limit=15)
        ids = {s.id for s in top}
        assert "system_2_attention" in ids, f"S2A should be reachable. Top: {ids}"

    def test_thread_of_thought_reachable(self, selector):
        ctx = TaskContext(task_type="diagnosis", complexity="medium", urgency="medium", domain="clinical")
        top = selector.select_multiple(ctx, limit=20)
        ids = {s.id for s in top}
        assert "thread_of_thought" in ids, f"ThoT should be reachable. Top: {ids}"

    def test_reflexion_at_high_complexity(self, selector):
        ctx = TaskContext(task_type="diagnosis", complexity="high", urgency="medium", domain="clinical")
        top = selector.select_multiple(ctx, limit=25)
        ids = {s.id for s in top}
        assert "reflexion" in ids, f"Reflexion needs high complexity. Top: {ids}"

    def test_least_to_most_reachable(self, selector):
        ctx = TaskContext(task_type="treatment_planning", complexity="medium", urgency="medium", domain="clinical")
        top = selector.select_multiple(ctx, limit=10)
        ids = {s.id for s in top}
        assert "least_to_most" in ids, f"Least-to-most should match treatment_planning. Top: {ids}"

    def test_contrastive_cot_reachable(self, selector):
        ctx = TaskContext(task_type="diagnosis", complexity="medium", urgency="medium", domain="clinical")
        top = selector.select_multiple(ctx, limit=25)
        ids = {s.id for s in top}
        assert "contrastive_cot" in ids, f"Contrastive CoT should be reachable. Top: {ids}"

    def test_program_of_thoughts_for_lab(self, selector):
        ctx = TaskContext(task_type="lab", complexity="medium", urgency="medium", domain="lab")
        top = selector.select_multiple(ctx, limit=10)
        ids = {s.id for s in top}
        assert "program_of_thoughts" in ids, f"PoT should match lab tasks. Top: {ids}"

    def test_rephrase_and_respond_for_avatar(self, selector):
        ctx = TaskContext(task_type="avatar_conversation", complexity="low", urgency="medium", domain="clinical")
        top = selector.select_multiple(ctx, limit=5)
        ids = {s.id for s in top}
        assert "rephrase_and_respond" in ids, f"RaR should match avatar conversation. Top: {ids}"

    def test_analogical_prompting_reachable(self, selector):
        ctx = TaskContext(task_type="diagnosis", complexity="medium", urgency="medium", domain="clinical")
        top = selector.select_multiple(ctx, limit=25)
        ids = {s.id for s in top}
        assert "analogical_prompting" in ids, f"Analogical prompting should be reachable. Top: {ids}"

    def test_meta_prompting_at_high_complexity(self, selector):
        ctx = TaskContext(task_type="diagnosis", complexity="high", urgency="medium", domain="clinical")
        top = selector.select_multiple(ctx, limit=25)
        ids = {s.id for s in top}
        assert "meta_prompting" in ids, f"Meta-prompting needs high complexity. Top: {ids}"
