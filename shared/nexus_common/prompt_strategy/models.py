"""Dataclass models for prompt strategies.

Mirrors the Persona dataclass pattern in ``identity/persona_registry.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StrategyWhenToUse:
    """Conditions under which a strategy is applicable."""

    task_types: list[str] = field(default_factory=list)
    min_complexity: str = "low"  # "low" | "medium" | "high"
    urgency: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StrategyWhenToUse":
        return cls(
            task_types=list(data.get("task_types") or []),
            min_complexity=str(data.get("min_complexity") or "low"),
            urgency=list(data.get("urgency") or []),
            domains=list(data.get("domains") or []),
        )


@dataclass
class StrategyTemplate:
    """Prompt template fragments applied by the strategy."""

    prefix: str = ""
    suffix: str = ""
    system_addendum: str = ""
    few_shot_examples: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StrategyTemplate":
        return cls(
            prefix=str(data.get("prefix") or ""),
            suffix=str(data.get("suffix") or ""),
            system_addendum=str(data.get("system_addendum") or ""),
            few_shot_examples=list(data.get("few_shot_examples") or []),
        )


@dataclass
class StrategySource:
    """Research paper or reference for the strategy."""

    paper: str = ""
    url: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StrategySource":
        return cls(
            paper=str(data.get("paper") or ""),
            url=str(data.get("url") or ""),
        )


@dataclass
class PromptStrategy:
    """A single prompt engineering strategy loaded from the registry."""

    id: str
    name: str
    description: str
    strategy_type: str  # "reasoning" | "exemplar" | "agentic" | "persona" | "formatting"
    when_to_use: StrategyWhenToUse
    template: StrategyTemplate
    parameters: dict[str, Any] = field(default_factory=dict)
    source: StrategySource = field(default_factory=StrategySource)
    version: str = "1.0"
    enabled: bool = True
    priority: int = 50  # lower = higher priority

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PromptStrategy":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]),
            description=str(data.get("description") or ""),
            strategy_type=str(data.get("strategy_type") or "reasoning"),
            when_to_use=StrategyWhenToUse.from_dict(data.get("when_to_use") or {}),
            template=StrategyTemplate.from_dict(data.get("template") or {}),
            parameters=dict(data.get("parameters") or {}),
            source=StrategySource.from_dict(data.get("source") or {}),
            version=str(data.get("version") or "1.0"),
            enabled=bool(data.get("enabled", True)),
            priority=int(data.get("priority", 50)),
        )
