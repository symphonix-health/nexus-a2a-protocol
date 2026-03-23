"""Tests for the PromptStrategyRegistry — loading, lookup, filtering, reload."""

from __future__ import annotations

import json
import os
import tempfile
import time

import pytest

from shared.nexus_common.prompt_strategy.models import PromptStrategy
from shared.nexus_common.prompt_strategy.registry import PromptStrategyRegistry, get_strategy_registry


# ── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def sample_data() -> dict:
    return {
        "$schema": "nexus:prompt_strategies:v1",
        "version": "1.0.0",
        "strategies": [
            {
                "id": "chain_of_thought",
                "name": "Chain of Thought",
                "description": "Step-by-step reasoning",
                "strategy_type": "reasoning",
                "when_to_use": {
                    "task_types": ["diagnosis", "differential"],
                    "min_complexity": "medium",
                    "urgency": ["low", "medium", "high"],
                    "domains": ["clinical", "pharmacy"],
                },
                "template": {
                    "prefix": "Think step by step:\n",
                    "suffix": "\nConclusion:",
                    "system_addendum": "Use chain-of-thought reasoning.",
                    "few_shot_examples": [],
                },
                "parameters": {"reasoning_depth": "detailed"},
                "source": {"paper": "Wei et al. 2022", "url": "https://arxiv.org/abs/2201.11903"},
                "version": "1.0",
                "enabled": True,
                "priority": 10,
            },
            {
                "id": "few_shot",
                "name": "Few-Shot",
                "description": "Exemplar-based",
                "strategy_type": "exemplar",
                "when_to_use": {
                    "task_types": ["imaging", "lab"],
                    "min_complexity": "low",
                    "urgency": ["low", "medium", "high", "critical"],
                    "domains": ["clinical", "imaging", "lab"],
                },
                "template": {
                    "prefix": "",
                    "suffix": "",
                    "system_addendum": "Follow the examples.",
                    "few_shot_examples": [{"input": "X-ray chest", "output": "Normal"}],
                },
                "parameters": {},
                "source": {"paper": "Brown et al. 2020", "url": ""},
                "version": "1.0",
                "enabled": True,
                "priority": 20,
            },
            {
                "id": "disabled_strategy",
                "name": "Disabled",
                "description": "Should not be loaded",
                "strategy_type": "reasoning",
                "when_to_use": {"task_types": ["diagnosis"], "min_complexity": "low", "urgency": ["low"], "domains": ["clinical"]},
                "template": {"prefix": "", "suffix": "", "system_addendum": "", "few_shot_examples": []},
                "parameters": {},
                "source": {"paper": "", "url": ""},
                "version": "1.0",
                "enabled": False,
                "priority": 99,
            },
        ],
    }


@pytest.fixture
def registry(sample_data: dict) -> PromptStrategyRegistry:
    return PromptStrategyRegistry(sample_data)


# ── Basic Loading ──────────────────────────────────────────────────────

def test_load_enabled_strategies(registry: PromptStrategyRegistry):
    """Only enabled strategies should be loaded."""
    assert len(registry.all()) == 2
    ids = {s.id for s in registry.all()}
    assert ids == {"chain_of_thought", "few_shot"}


def test_disabled_strategies_excluded(registry: PromptStrategyRegistry):
    assert registry.get("disabled_strategy") is None


# ── Lookup ─────────────────────────────────────────────────────────────

def test_get_by_id(registry: PromptStrategyRegistry):
    cot = registry.get("chain_of_thought")
    assert cot is not None
    assert cot.name == "Chain of Thought"
    assert cot.strategy_type == "reasoning"
    assert cot.priority == 10


def test_get_unknown_returns_none(registry: PromptStrategyRegistry):
    assert registry.get("nonexistent") is None


def test_require_known(registry: PromptStrategyRegistry):
    cot = registry.require("chain_of_thought")
    assert cot.id == "chain_of_thought"


def test_require_unknown_raises(registry: PromptStrategyRegistry):
    with pytest.raises(KeyError, match="nonexistent"):
        registry.require("nonexistent")


# ── Filtering ──────────────────────────────────────────────────────────

def test_filter_by_task_type(registry: PromptStrategyRegistry):
    results = registry.filter(task_type="diagnosis")
    assert len(results) == 1
    assert results[0].id == "chain_of_thought"


def test_filter_by_domain(registry: PromptStrategyRegistry):
    results = registry.filter(domain="imaging")
    assert len(results) == 1
    assert results[0].id == "few_shot"


def test_filter_by_strategy_type(registry: PromptStrategyRegistry):
    results = registry.filter(strategy_type="reasoning")
    assert len(results) == 1
    assert results[0].id == "chain_of_thought"


def test_filter_by_max_complexity(registry: PromptStrategyRegistry):
    # low complexity should only return few_shot (min_complexity=low)
    results = registry.filter(max_complexity="low")
    ids = {s.id for s in results}
    assert "few_shot" in ids
    assert "chain_of_thought" not in ids  # needs medium


def test_filter_combined(registry: PromptStrategyRegistry):
    results = registry.filter(task_type="diagnosis", domain="clinical", strategy_type="reasoning")
    assert len(results) == 1
    assert results[0].id == "chain_of_thought"


def test_filter_no_match(registry: PromptStrategyRegistry):
    results = registry.filter(task_type="nonexistent_task")
    assert results == []


def test_filter_returns_sorted_by_priority(registry: PromptStrategyRegistry):
    results = registry.filter(domain="clinical")
    priorities = [s.priority for s in results]
    assert priorities == sorted(priorities)


# ── Model Fields ───────────────────────────────────────────────────────

def test_strategy_fields_populated(registry: PromptStrategyRegistry):
    cot = registry.require("chain_of_thought")
    assert cot.description == "Step-by-step reasoning"
    assert cot.template.prefix == "Think step by step:\n"
    assert cot.template.suffix == "\nConclusion:"
    assert cot.template.system_addendum == "Use chain-of-thought reasoning."
    assert cot.source.paper == "Wei et al. 2022"
    assert cot.when_to_use.task_types == ["diagnosis", "differential"]
    assert cot.when_to_use.min_complexity == "medium"
    assert cot.parameters == {"reasoning_depth": "detailed"}


def test_few_shot_examples_populated(registry: PromptStrategyRegistry):
    fs = registry.require("few_shot")
    assert len(fs.template.few_shot_examples) == 1
    assert fs.template.few_shot_examples[0]["input"] == "X-ray chest"


# ── Schema / Version ──────────────────────────────────────────────────

def test_schema_version(registry: PromptStrategyRegistry):
    assert registry.schema_version == "nexus:prompt_strategies:v1"
    assert registry.data_version == "1.0.0"


# ── Hot-Reload ─────────────────────────────────────────────────────────

def test_reload_if_changed(sample_data: dict):
    """Write JSON to a temp file, load registry, modify file, reload."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(sample_data, f)
        tmp_path = f.name

    try:
        reg = PromptStrategyRegistry(sample_data, file_path=tmp_path)
        assert len(reg.all()) == 2

        # No change — should return False
        assert reg.reload_if_changed() is False

        # Modify the file: add a new strategy
        time.sleep(0.05)  # ensure mtime differs
        sample_data["strategies"].append({
            "id": "step_back",
            "name": "Step Back",
            "description": "Abstraction first",
            "strategy_type": "reasoning",
            "when_to_use": {"task_types": ["diagnosis"], "min_complexity": "low", "urgency": ["low"], "domains": ["clinical"]},
            "template": {"prefix": "", "suffix": "", "system_addendum": "Step back.", "few_shot_examples": []},
            "parameters": {},
            "source": {"paper": "", "url": ""},
            "version": "1.0",
            "enabled": True,
            "priority": 35,
        })
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(sample_data, f)

        # Now should reload
        assert reg.reload_if_changed() is True
        assert len(reg.all()) == 3
        assert reg.get("step_back") is not None
    finally:
        os.unlink(tmp_path)


def test_reload_no_file_path():
    """Registry without file_path should not attempt reload."""
    reg = PromptStrategyRegistry({"strategies": []})
    assert reg.reload_if_changed() is False


# ── Load from real config ──────────────────────────────────────────────

def test_load_real_config():
    """Verify the actual config/prompt_strategies.json loads correctly."""
    registry = get_strategy_registry()
    strategies = registry.all()
    assert len(strategies) >= 20, f"Expected ≥20 strategies, got {len(strategies)}"
    # Verify all required strategies exist
    for expected_id in [
        # Original 8
        "chain_of_thought", "few_shot", "self_consistency",
        "tree_of_thought", "react", "step_back",
        "role_prompting", "structured_output",
        # 12 research-backed additions
        "medprompt", "chain_of_verification", "cumulative_reasoning",
        "system_2_attention", "thread_of_thought", "reflexion",
        "least_to_most", "contrastive_cot", "analogical_prompting",
        "meta_prompting", "program_of_thoughts", "rephrase_and_respond",
    ]:
        assert registry.get(expected_id) is not None, f"Missing strategy: {expected_id}"


def test_all_real_strategies_have_required_fields():
    """Every loaded strategy must have non-empty id, name, template."""
    registry = get_strategy_registry()
    for s in registry.all():
        assert s.id, f"Strategy missing id: {s}"
        assert s.name, f"Strategy {s.id} missing name"
        assert s.template is not None, f"Strategy {s.id} missing template"
        assert s.when_to_use is not None, f"Strategy {s.id} missing when_to_use"
