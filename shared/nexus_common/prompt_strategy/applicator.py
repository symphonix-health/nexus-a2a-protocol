"""Apply a selected strategy's template to existing prompt pairs.

Thin utility that keeps strategy application logic out of the prompt
constructors themselves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import PromptStrategy


def apply_strategy(
    strategy: PromptStrategy | None,
    system_prompt: str,
    user_prompt: str,
) -> tuple[str, str]:
    """Apply a strategy's template modifications to existing prompts.

    If *strategy* is ``None``, returns prompts unchanged (safe no-op for
    backward compatibility).
    """
    if strategy is None:
        return system_prompt, user_prompt

    tpl = strategy.template

    # 1. Append system_addendum to system prompt
    enhanced_system = system_prompt
    if tpl.system_addendum:
        enhanced_system = f"{system_prompt}\n\n{tpl.system_addendum}"

    # 2. Wrap user prompt with prefix / suffix
    enhanced_user = user_prompt
    if tpl.prefix:
        enhanced_user = f"{tpl.prefix}{enhanced_user}"
    if tpl.suffix:
        enhanced_user = f"{enhanced_user}{tpl.suffix}"

    # 3. Append few-shot examples to system prompt (if any)
    if tpl.few_shot_examples:
        examples_text = "\n\n".join(
            f"Example input: {ex.get('input', '')}\nExample output: {ex.get('output', '')}"
            for ex in tpl.few_shot_examples
        )
        enhanced_system = f"{enhanced_system}\n\n{examples_text}"

    return enhanced_system, enhanced_user
