"""Tests for apply_strategy — prompt enhancement logic."""

from __future__ import annotations

import pytest

from shared.nexus_common.prompt_strategy.applicator import apply_strategy
from shared.nexus_common.prompt_strategy.models import (
    PromptStrategy,
    StrategySource,
    StrategyTemplate,
    StrategyWhenToUse,
)


# ── Helpers ────────────────────────────────────────────────────────────

def _make_strategy(
    *,
    prefix: str = "",
    suffix: str = "",
    system_addendum: str = "",
    few_shot_examples: list[dict[str, str]] | None = None,
) -> PromptStrategy:
    return PromptStrategy(
        id="test",
        name="Test Strategy",
        description="For testing",
        strategy_type="reasoning",
        when_to_use=StrategyWhenToUse(),
        template=StrategyTemplate(
            prefix=prefix,
            suffix=suffix,
            system_addendum=system_addendum,
            few_shot_examples=few_shot_examples or [],
        ),
        parameters={},
        source=StrategySource(),
    )


# ── Tests ──────────────────────────────────────────────────────────────

def test_none_strategy_passthrough():
    """None strategy must return prompts completely unchanged."""
    sys, usr = apply_strategy(None, "system text", "user text")
    assert sys == "system text"
    assert usr == "user text"


def test_system_addendum_appended():
    strategy = _make_strategy(system_addendum="Think step by step.")
    sys, usr = apply_strategy(strategy, "You are a doctor.", "What is the diagnosis?")
    assert sys == "You are a doctor.\n\nThink step by step."
    assert usr == "What is the diagnosis?"


def test_prefix_prepended():
    strategy = _make_strategy(prefix="Step by step:\n")
    sys, usr = apply_strategy(strategy, "System", "User question")
    assert sys == "System"
    assert usr == "Step by step:\nUser question"


def test_suffix_appended():
    strategy = _make_strategy(suffix="\nFinal answer:")
    sys, usr = apply_strategy(strategy, "System", "User question")
    assert usr == "User question\nFinal answer:"


def test_prefix_and_suffix_combined():
    strategy = _make_strategy(prefix="BEGIN:\n", suffix="\n:END")
    sys, usr = apply_strategy(strategy, "System", "middle")
    assert usr == "BEGIN:\nmiddle\n:END"


def test_few_shot_examples_appended_to_system():
    strategy = _make_strategy(
        few_shot_examples=[
            {"input": "chest pain", "output": "cardiac workup"},
            {"input": "headache", "output": "neuro exam"},
        ],
    )
    sys, usr = apply_strategy(strategy, "Base system", "User input")
    assert "Example input: chest pain" in sys
    assert "Example output: cardiac workup" in sys
    assert "Example input: headache" in sys
    assert "Example output: neuro exam" in sys
    assert usr == "User input"


def test_all_template_fields_combined():
    strategy = _make_strategy(
        prefix="Think:\n",
        suffix="\nAnswer:",
        system_addendum="Reason carefully.",
        few_shot_examples=[{"input": "A", "output": "B"}],
    )
    sys, usr = apply_strategy(strategy, "Base", "Question")
    assert sys.startswith("Base\n\nReason carefully.")
    assert "Example input: A" in sys
    assert usr == "Think:\nQuestion\nAnswer:"


def test_empty_addendum_no_extra_newlines():
    strategy = _make_strategy(system_addendum="")
    sys, _ = apply_strategy(strategy, "Base system", "user")
    assert sys == "Base system"  # No trailing newlines added


def test_empty_prefix_suffix_no_change():
    strategy = _make_strategy(prefix="", suffix="")
    _, usr = apply_strategy(strategy, "sys", "user text")
    assert usr == "user text"
