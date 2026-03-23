"""Tests for PromptStrategySelector — strategy selection logic."""

from __future__ import annotations

import pytest

from shared.nexus_common.prompt_strategy.models import PromptStrategy
from shared.nexus_common.prompt_strategy.registry import PromptStrategyRegistry, get_strategy_registry
from shared.nexus_common.prompt_strategy.selector import PromptStrategySelector, TaskContext


# ── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def registry() -> PromptStrategyRegistry:
    """Use the real config/prompt_strategies.json."""
    return get_strategy_registry()


@pytest.fixture
def selector(registry: PromptStrategyRegistry) -> PromptStrategySelector:
    return PromptStrategySelector(registry)


# ── Selection ──────────────────────────────────────────────────────────

def test_select_structured_output_for_imaging(selector: PromptStrategySelector):
    """Imaging at low complexity should get structured_output (priority 1)."""
    ctx = TaskContext(task_type="imaging", complexity="low", urgency="medium", domain="imaging")
    result = selector.select(ctx)
    assert result is not None
    assert result.id == "structured_output"  # priority 1, lowest


def test_select_returns_lowest_priority_match(selector: PromptStrategySelector):
    """For diagnosis + medium complexity, structured_output (1) beats role_prompting (5) beats CoT (10)."""
    ctx = TaskContext(task_type="diagnosis", complexity="medium", urgency="medium", domain="clinical")
    result = selector.select(ctx)
    assert result is not None
    assert result.id == "structured_output"  # priority 1


def test_select_returns_none_for_unmatched_context(selector: PromptStrategySelector):
    ctx = TaskContext(task_type="totally_unknown_task", complexity="low", urgency="low", domain="unknown_domain")
    result = selector.select(ctx)
    assert result is None


def test_urgency_critical_excludes_self_consistency(selector: PromptStrategySelector):
    """Self-consistency only allows low/medium urgency — critical should exclude it."""
    ctx = TaskContext(task_type="diagnosis", complexity="high", urgency="critical", domain="clinical")
    result = selector.select(ctx)
    # Should not be self_consistency (urgency filter)
    if result is not None:
        assert result.id != "self_consistency"


def test_low_complexity_excludes_high_min(selector: PromptStrategySelector):
    """Low complexity should not select strategies with min_complexity=high."""
    ctx = TaskContext(task_type="diagnosis", complexity="low", urgency="low", domain="clinical")
    result = selector.select(ctx)
    if result is not None:
        # self_consistency and tree_of_thought require high complexity
        assert result.id not in {"self_consistency", "tree_of_thought"}


def test_high_complexity_includes_all(selector: PromptStrategySelector):
    """High complexity should include strategies requiring medium or high."""
    ctx = TaskContext(task_type="diagnosis", complexity="high", urgency="medium", domain="clinical")
    results = selector.select_multiple(ctx, limit=25)
    ids = {s.id for s in results}
    # Should include strategies up to high complexity
    assert "chain_of_thought" in ids  # min=medium
    assert "self_consistency" in ids  # min=high
    assert "cumulative_reasoning" in ids  # min=high


# ── select_multiple ────────────────────────────────────────────────────

def test_select_multiple_returns_sorted(selector: PromptStrategySelector):
    ctx = TaskContext(task_type="diagnosis", complexity="high", urgency="medium", domain="clinical")
    results = selector.select_multiple(ctx, limit=5)
    assert len(results) >= 2
    priorities = [s.priority for s in results]
    assert priorities == sorted(priorities)


def test_select_multiple_respects_limit(selector: PromptStrategySelector):
    ctx = TaskContext(task_type="diagnosis", complexity="high", urgency="medium", domain="clinical")
    results = selector.select_multiple(ctx, limit=2)
    assert len(results) <= 2


def test_select_multiple_empty_for_no_match(selector: PromptStrategySelector):
    ctx = TaskContext(task_type="nonexistent", complexity="low", urgency="low", domain="nonexistent")
    results = selector.select_multiple(ctx, limit=5)
    assert results == []


# ── TaskContext ─────────────────────────────────────────────────────────

def test_task_context_defaults():
    ctx = TaskContext(task_type="diagnosis")
    assert ctx.complexity == "medium"
    assert ctx.urgency == "medium"
    assert ctx.domain == "clinical"


def test_task_context_full():
    ctx = TaskContext(task_type="lab", complexity="high", urgency="critical", domain="lab")
    assert ctx.task_type == "lab"
    assert ctx.complexity == "high"
    assert ctx.urgency == "critical"
    assert ctx.domain == "lab"
