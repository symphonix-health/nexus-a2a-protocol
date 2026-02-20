"""LLM-enabled handler for generic agents.

This module is designed to be opt-in. When enabled by environment variable
NEXUS_AGENT_LLM_ENABLED=1, generic agents can use domain-specific prompts to
produce realistic outputs based on an incoming clinical_context object.

Initially this is a no-op shim that returns None (caller should fallback to
startup-safe defaults). Later we will wire it into generic_demo_agent.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .clinical_prompts import diagnosis_prompt, imaging_prompt, lab_prompt, pharmacy_prompt
from .openai_helper import llm_chat


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


def try_llm_result(method: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """Attempt to produce a realistic result for a given method.

    Returns None if LLM is not enabled/available or if the method is unhandled.
    """
    if not llm_enabled():
        return None

    clinical_context = (
        params.get("clinical_context") if isinstance(params.get("clinical_context"), dict) else {}
    )
    method_l = (method or "").lower()

    try:
        if "imaging" in method_l:
            orders = (params.get("orders") or []) if isinstance(params.get("orders"), list) else []
            study = orders[0]["type"] if orders and isinstance(orders[0], dict) else "unspecified"
            system, user = imaging_prompt(clinical_context, study)
            content = llm_chat(system, user)
            return {"imaging_report": _parse_llm_content(content)}

        if "pharmacy" in method_l:
            system, user = pharmacy_prompt(clinical_context)
            content = llm_chat(system, user)
            return {"pharmacy_plan": _parse_llm_content(content)}

        if "diagnosis" in method_l:
            system, user = diagnosis_prompt(clinical_context)
            content = llm_chat(system, user)
            return {"diagnosis_assessment": _parse_llm_content(content)}

        if "lab" in method_l or "labs" in method_l:
            tests = params.get("tests") or []
            system, user = lab_prompt(clinical_context, tests if isinstance(tests, list) else [])
            content = llm_chat(system, user)
            return {"lab_panel": _parse_llm_content(content)}
    except Exception:
        # On any error, silently allow fallback to the startup-safe handler
        return None

    return None
    return None
