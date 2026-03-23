"""Prompt strategy registry — load and query strategies from JSON.

Mirrors the PersonaRegistry pattern in ``identity/persona_registry.py``.

Usage::

    from shared.nexus_common.prompt_strategy import get_strategy_registry

    registry = get_strategy_registry()
    cot = registry.get("chain_of_thought")
    reasoning_strategies = registry.filter(strategy_type="reasoning")
"""

from __future__ import annotations

import json
import logging
import os
import threading
from functools import lru_cache
from typing import Any

from .models import PromptStrategy

logger = logging.getLogger(__name__)

_STRATEGIES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "config", "prompt_strategies.json"
)

# Complexity ordering for filter comparisons
COMPLEXITY_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2}


class PromptStrategyRegistry:
    """In-memory registry of prompt strategies keyed by strategy id."""

    def __init__(self, data: dict[str, Any], *, file_path: str | None = None) -> None:
        self._raw = data
        self._strategies: dict[str, PromptStrategy] = {}
        for s in data.get("strategies", []):
            try:
                ps = PromptStrategy.from_dict(s)
                if ps.enabled:
                    self._strategies[ps.id] = ps
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipping malformed strategy entry: %s", exc)
        self._file_path = file_path
        self._last_mtime: float = 0.0
        self._lock = threading.Lock()
        if file_path:
            try:
                self._last_mtime = os.path.getmtime(file_path)
            except OSError:
                pass

    # Lookup -----------------------------------------------------------------

    def get(self, strategy_id: str) -> PromptStrategy | None:
        """Return a strategy by id, or None if not found."""
        return self._strategies.get(strategy_id)

    def require(self, strategy_id: str) -> PromptStrategy:
        """Return a strategy by id, or raise KeyError."""
        s = self.get(strategy_id)
        if s is None:
            raise KeyError(f"Unknown strategy_id '{strategy_id}'")
        return s

    def filter(
        self,
        *,
        task_type: str | None = None,
        domain: str | None = None,
        strategy_type: str | None = None,
        max_complexity: str | None = None,
    ) -> list[PromptStrategy]:
        """Return strategies matching all provided criteria."""
        results = list(self._strategies.values())
        if task_type:
            results = [s for s in results if task_type in s.when_to_use.task_types]
        if domain:
            results = [s for s in results if domain in s.when_to_use.domains]
        if strategy_type:
            results = [s for s in results if s.strategy_type == strategy_type]
        if max_complexity:
            max_ord = COMPLEXITY_ORDER.get(max_complexity, 1)
            results = [
                s
                for s in results
                if COMPLEXITY_ORDER.get(s.when_to_use.min_complexity, 0) <= max_ord
            ]
        return sorted(results, key=lambda s: s.priority)

    def all(self) -> list[PromptStrategy]:
        """Return all enabled strategies sorted by priority."""
        return sorted(self._strategies.values(), key=lambda s: s.priority)

    @property
    def schema_version(self) -> str:
        return str(self._raw.get("$schema", ""))

    @property
    def data_version(self) -> str:
        return str(self._raw.get("version", ""))

    # Hot-reload -------------------------------------------------------------

    def reload_if_changed(self) -> bool:
        """Check file mtime; reload strategies if the file has changed.

        Returns True if a reload was performed, False otherwise.
        Thread-safe via a lock to prevent concurrent reloads.
        """
        if not self._file_path:
            return False
        try:
            current_mtime = os.path.getmtime(self._file_path)
        except OSError:
            return False
        if current_mtime <= self._last_mtime:
            return False

        with self._lock:
            # Double-check after acquiring lock
            try:
                current_mtime = os.path.getmtime(self._file_path)
            except OSError:
                return False
            if current_mtime <= self._last_mtime:
                return False

            logger.info("Prompt strategy file changed, reloading: %s", self._file_path)
            try:
                with open(self._file_path, encoding="utf-8") as fh:
                    data = json.load(fh)
                new_strategies: dict[str, PromptStrategy] = {}
                for s in data.get("strategies", []):
                    try:
                        ps = PromptStrategy.from_dict(s)
                        if ps.enabled:
                            new_strategies[ps.id] = ps
                    except (KeyError, TypeError, ValueError) as exc:
                        logger.warning("Skipping malformed strategy on reload: %s", exc)
                self._raw = data
                self._strategies = new_strategies
                self._last_mtime = current_mtime
                logger.info("Reloaded %d strategies", len(new_strategies))
                return True
            except (json.JSONDecodeError, OSError) as exc:
                logger.error("Failed to reload prompt strategies: %s", exc)
                return False


@lru_cache(maxsize=1)
def _load_registry() -> PromptStrategyRegistry:
    path = os.path.normpath(_STRATEGIES_PATH)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return PromptStrategyRegistry(data, file_path=path)


def get_strategy_registry() -> PromptStrategyRegistry:
    """Return the singleton PromptStrategyRegistry.

    Loaded once from ``config/prompt_strategies.json``.
    Call ``registry.reload_if_changed()`` to pick up edits without restart.
    """
    registry = _load_registry()
    registry.reload_if_changed()
    return registry
