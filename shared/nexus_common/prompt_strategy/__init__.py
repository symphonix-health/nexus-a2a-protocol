"""Prompt Strategy Registry — data-driven prompt engineering strategies.

Usage::

    from shared.nexus_common.prompt_strategy import (
        get_strategy_registry,
        PromptStrategySelector,
        TaskContext,
        apply_strategy,
    )

    registry = get_strategy_registry()
    selector = PromptStrategySelector(registry)
    ctx = TaskContext(task_type="diagnosis", complexity="medium", urgency="high", domain="clinical")
    strategy = selector.select(ctx)
    system, user = apply_strategy(strategy, system_prompt, user_prompt)
"""

from .applicator import apply_strategy
from .models import PromptStrategy, StrategySource, StrategyTemplate, StrategyWhenToUse
from .registry import PromptStrategyRegistry, get_strategy_registry
from .selector import PromptStrategySelector, TaskContext

__all__ = [
    "PromptStrategy",
    "PromptStrategyRegistry",
    "PromptStrategySelector",
    "StrategySource",
    "StrategyTemplate",
    "StrategyWhenToUse",
    "TaskContext",
    "apply_strategy",
    "get_strategy_registry",
]
