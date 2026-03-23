"""Strategy selector — picks the best prompt strategy for a given task context.

Rule-based by default.  The ``select()`` interface (TaskContext → PromptStrategy)
is a stable contract so an LLM-as-router can replace it later without changing
any call-site.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .registry import COMPLEXITY_ORDER

if TYPE_CHECKING:
    from .models import PromptStrategy
    from .registry import PromptStrategyRegistry


@dataclass
class TaskContext:
    """Describes the current task so the selector can pick a strategy."""

    task_type: str  # e.g. "diagnosis", "imaging", "lab", "avatar_conversation"
    complexity: str = "medium"  # "low" | "medium" | "high"
    urgency: str = "medium"  # "low" | "medium" | "high" | "critical"
    domain: str = "clinical"  # "clinical" | "lab" | "imaging" | "pharmacy" | "operations"


class PromptStrategySelector:
    """Rule-based strategy selector.

    Filters candidates by task_type, domain, complexity, and urgency then
    returns the highest-priority (lowest ``priority`` number) match.
    """

    def __init__(self, registry: PromptStrategyRegistry) -> None:
        self._registry = registry

    def select(self, ctx: TaskContext) -> PromptStrategy | None:
        """Pick the single best-fit strategy for *ctx*.

        Returns ``None`` when no strategy matches (callers should fall back to
        their existing prompt logic).
        """
        candidates = self._registry.filter(
            task_type=ctx.task_type,
            domain=ctx.domain,
        )
        # Complexity filter: strategy min_complexity must be ≤ task complexity
        task_ord = COMPLEXITY_ORDER.get(ctx.complexity, 1)
        candidates = [
            s
            for s in candidates
            if COMPLEXITY_ORDER.get(s.when_to_use.min_complexity, 0) <= task_ord
        ]
        # Urgency filter: task urgency must be in strategy's allowed urgency list
        candidates = [s for s in candidates if ctx.urgency in s.when_to_use.urgency]
        if not candidates:
            return None
        # Already sorted by priority from registry.filter()
        return candidates[0]

    def select_multiple(self, ctx: TaskContext, limit: int = 3) -> list[PromptStrategy]:
        """Return top *limit* matching strategies (for composing multiple).

        Useful when you want to layer, e.g., role_prompting + chain_of_thought.
        """
        candidates = self._registry.filter(
            task_type=ctx.task_type,
            domain=ctx.domain,
        )
        task_ord = COMPLEXITY_ORDER.get(ctx.complexity, 1)
        candidates = [
            s
            for s in candidates
            if COMPLEXITY_ORDER.get(s.when_to_use.min_complexity, 0) <= task_ord
        ]
        candidates = [s for s in candidates if ctx.urgency in s.when_to_use.urgency]
        return candidates[:limit]
