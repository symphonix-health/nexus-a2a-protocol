"""LLM-enabled handler for generic agents.

This module is designed to be opt-in. When enabled by environment variable
NEXUS_AGENT_LLM_ENABLED=1, generic agents can use domain-specific prompts to
produce realistic outputs based on an incoming clinical_context object.

Strategy selection is automatic: the handler derives a TaskContext from the
method name and clinical_context, picks the best prompt strategy from the
registry, and passes it to the domain-specific prompt function.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from .clinical_prompts import diagnosis_prompt, imaging_prompt, lab_prompt, pharmacy_prompt
from .openai_helper import llm_chat

logger = logging.getLogger(__name__)

# ── Method-to-TaskContext mapping ──────────────────────────────────────

_METHOD_TASK_MAP: dict[str, tuple[str, str]] = {
    # method_keyword → (task_type, domain)
    "imaging": ("imaging", "imaging"),
    "pharmacy": ("pharmacy", "pharmacy"),
    "diagnosis": ("diagnosis", "clinical"),
    "lab": ("lab", "lab"),
    "labs": ("lab", "lab"),
}


def llm_enabled() -> bool:
    return os.getenv("NEXUS_AGENT_LLM_ENABLED", "0").strip() not in ("", "0", "false", "False")


def _parse_llm_content(content: str) -> dict[str, Any] | str:
    """Best-effort JSON parsing for LLM responses."""
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return content


def _derive_urgency(clinical_context: dict[str, Any]) -> str:
    """Extract urgency from clinical_context, default to medium."""
    profile = clinical_context.get("patient_profile")
    if isinstance(profile, dict):
        return str(profile.get("urgency") or "medium").lower()
    return "medium"


def _derive_complexity(clinical_context: dict[str, Any]) -> str:
    """Infer complexity from clinical_context signals."""
    history = clinical_context.get("medical_history")
    if isinstance(history, dict):
        conditions = history.get("conditions") or history.get("active_conditions") or []
        medications = history.get("medications") or history.get("active_medications") or []
        if len(conditions) >= 3 or len(medications) >= 5:
            return "high"
        if conditions or medications:
            return "medium"
    return "medium"


def _select_strategy_for_method(
    method: str, clinical_context: dict[str, Any]
) -> Any:
    """Select a prompt strategy based on the method and clinical context.

    Returns a PromptStrategy or None (graceful fallback).
    """
    try:
        from .prompt_strategy import PromptStrategySelector, TaskContext, get_strategy_registry

        method_l = (method or "").lower()
        task_type = "clinical_reasoning"
        domain = "clinical"

        for keyword, (tt, dom) in _METHOD_TASK_MAP.items():
            if keyword in method_l:
                task_type = tt
                domain = dom
                break

        registry = get_strategy_registry()
        selector = PromptStrategySelector(registry)
        ctx = TaskContext(
            task_type=task_type,
            complexity=_derive_complexity(clinical_context),
            urgency=_derive_urgency(clinical_context),
            domain=domain,
        )
        strategy = selector.select(ctx)
        if strategy:
            logger.debug(
                "Strategy selected for %s: %s (priority=%d)",
                method, strategy.id, strategy.priority,
            )
        return strategy
    except Exception:
        logger.debug("Strategy selection unavailable for %s, using defaults", method)
        return None


def try_llm_result(method: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """Attempt to produce a realistic result for a given method.

    Returns None if LLM is not enabled/available or if the method is unhandled.
    Automatically selects and applies the best prompt strategy for the task.
    """
    if not llm_enabled():
        return None

    clinical_context = (
        params.get("clinical_context") if isinstance(params.get("clinical_context"), dict) else {}
    )
    method_l = (method or "").lower()

    # Select strategy once for this call
    strategy = _select_strategy_for_method(method, clinical_context)

    try:
        if "imaging" in method_l:
            orders = (params.get("orders") or []) if isinstance(params.get("orders"), list) else []
            study = orders[0]["type"] if orders and isinstance(orders[0], dict) else "unspecified"
            system, user = imaging_prompt(clinical_context, study, strategy=strategy)
            content = llm_chat(system, user)
            return {"imaging_report": _parse_llm_content(content)}

        if "pharmacy" in method_l:
            system, user = pharmacy_prompt(clinical_context, strategy=strategy)
            content = llm_chat(system, user)
            return {"pharmacy_plan": _parse_llm_content(content)}

        if "diagnosis" in method_l:
            system, user = diagnosis_prompt(clinical_context, strategy=strategy)
            content = llm_chat(system, user)
            return {"diagnosis_assessment": _parse_llm_content(content)}

        if "lab" in method_l or "labs" in method_l:
            tests = params.get("tests") or []
            system, user = lab_prompt(clinical_context, tests if isinstance(tests, list) else [], strategy=strategy)
            content = llm_chat(system, user)
            return {"lab_panel": _parse_llm_content(content)}
    except Exception:
        # On any error, silently allow fallback to the startup-safe handler
        return None

    return None
