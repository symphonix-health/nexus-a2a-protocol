#!/usr/bin/env python3
"""HelixCare canonical patient-visit scenarios (definitive set of 10)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import sys
import time

# Ensure Unicode output works on Windows consoles with narrow codepages
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.nexus_common.auth import mint_jwt
from shared.nexus_common.ids import make_trace_id
from shared.nexus_common.redaction import redact_payload
from shared.nexus_common.trace import TraceRun, TraceStepEvent

# Agent URLs loaded from seed database (sourced from config/agents.json)
from shared.nexus_common.seed_db import get_seed_db as _get_seed_db

BASE_URLS: dict[str, str] = _get_seed_db().get_all_agent_urls()
ON_DEMAND_GATEWAY_URL = os.getenv("NEXUS_ON_DEMAND_GATEWAY_URL", "").strip().rstrip("/")

RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class RetryRuntimeConfig:
    mode: str
    max_rpc_attempts: int
    base_retry_delay_seconds: float
    max_retry_delay_seconds: float
    max_retry_budget_seconds: float
    connect_timeout_seconds: float
    read_timeout_seconds: float
    max_inflight_per_endpoint: int


RETRY_MODE_CONFIGS: dict[str, RetryRuntimeConfig] = {
    "strict-zero": RetryRuntimeConfig(
        mode="strict-zero",
        max_rpc_attempts=10,
        base_retry_delay_seconds=0.2,
        max_retry_delay_seconds=2.0,
        max_retry_budget_seconds=45.0,
        connect_timeout_seconds=8.0,
        read_timeout_seconds=35.0,
        max_inflight_per_endpoint=4,
    ),
    "balanced": RetryRuntimeConfig(
        mode="balanced",
        max_rpc_attempts=7,
        base_retry_delay_seconds=0.12,
        max_retry_delay_seconds=1.2,
        max_retry_budget_seconds=20.0,
        connect_timeout_seconds=6.0,
        read_timeout_seconds=25.0,
        max_inflight_per_endpoint=8,
    ),
    "fast": RetryRuntimeConfig(
        mode="fast",
        max_rpc_attempts=4,
        base_retry_delay_seconds=0.05,
        max_retry_delay_seconds=0.5,
        max_retry_budget_seconds=5.0,
        connect_timeout_seconds=3.0,
        read_timeout_seconds=10.0,
        max_inflight_per_endpoint=12,
    ),
}

ACTIVE_RETRY_MODE = "balanced"
ACTIVE_RETRY_CONFIG = RETRY_MODE_CONFIGS[ACTIVE_RETRY_MODE]


def normalize_agent_alias(agent: str) -> str:
    """Normalize agent alias for direct/gateway routing."""
    value = agent.strip().lower().replace("-", "_")
    if value in BASE_URLS:
        return value
    for suffix in ("_agent", "_scheduler", "_service"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    if value == "care_coordinator":
        return "coordinator"
    preserved = f"{value}_agent"
    if preserved in BASE_URLS:
        return preserved
    return value


def resolve_agent_rpc_url(agent: str, gateway_url: str | None = None) -> str:
    """Resolve per-agent RPC URL in direct or on-demand gateway mode."""
    alias = normalize_agent_alias(agent)
    gateway = (
        (gateway_url if gateway_url is not None else ON_DEMAND_GATEWAY_URL).strip().rstrip("/")
    )
    if gateway:
        return f"{gateway}/rpc/{alias}"
    if alias not in BASE_URLS:
        raise KeyError(f"Unknown agent alias '{agent}'")
    return f"{BASE_URLS[alias].rstrip('/')}/rpc"


def _build_rpc_endpoint_limiters(config: RetryRuntimeConfig) -> dict[str, asyncio.Semaphore]:
    return {
        resolve_agent_rpc_url(agent): asyncio.Semaphore(config.max_inflight_per_endpoint)
        for agent in BASE_URLS
    }


RPC_ENDPOINT_LIMITERS = _build_rpc_endpoint_limiters(ACTIVE_RETRY_CONFIG)


def configure_retry_mode(mode: str) -> RetryRuntimeConfig:
    """Configure retry behavior profile for scenario execution runtime."""
    normalized_mode = mode.strip().lower().replace("_", "-")
    if normalized_mode not in RETRY_MODE_CONFIGS:
        options = ", ".join(sorted(RETRY_MODE_CONFIGS))
        raise ValueError(f"Unknown retry mode '{mode}'. Expected one of: {options}")

    config = RETRY_MODE_CONFIGS[normalized_mode]

    global ACTIVE_RETRY_MODE
    global ACTIVE_RETRY_CONFIG
    global RPC_ENDPOINT_LIMITERS

    ACTIVE_RETRY_MODE = normalized_mode
    ACTIVE_RETRY_CONFIG = config
    RPC_ENDPOINT_LIMITERS = _build_rpc_endpoint_limiters(config)
    return config


def configure_gateway_url(gateway_url: str | None) -> str:
    """Configure optional on-demand gateway routing for all agent RPC."""
    normalized = (gateway_url or "").strip().rstrip("/")
    global ON_DEMAND_GATEWAY_URL
    global RPC_ENDPOINT_LIMITERS

    ON_DEMAND_GATEWAY_URL = normalized
    RPC_ENDPOINT_LIMITERS = _build_rpc_endpoint_limiters(ACTIVE_RETRY_CONFIG)
    return ON_DEMAND_GATEWAY_URL


def _load_retry_mode_from_env() -> RetryRuntimeConfig:
    """Load optional retry mode from env; fallback to balanced on bad input."""
    env_mode = os.getenv("HELIXCARE_RETRY_MODE", "balanced")
    try:
        return configure_retry_mode(env_mode)
    except ValueError as exc:
        print(f"⚠ Invalid HELIXCARE_RETRY_MODE '{env_mode}': {exc}")
        print("⚠ Falling back to 'balanced'")
        return configure_retry_mode("balanced")


_load_retry_mode_from_env()


def _retry_delay_seconds(attempt_number: int) -> float:
    """Return bounded exponential backoff with jitter for retry attempts."""
    exponential = ACTIVE_RETRY_CONFIG.base_retry_delay_seconds * (2 ** max(0, attempt_number - 1))
    jitter = random.uniform(0.0, min(0.25, exponential))
    return min(ACTIVE_RETRY_CONFIG.max_retry_delay_seconds, exponential + jitter)


def _is_retriable_error(exc: Exception) -> bool:
    """Return whether a failed request should be retried."""
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code in RETRYABLE_STATUS_CODES

    # httpx-level retryable errors
    if isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.WriteError,
            httpx.ReadError,
            httpx.RemoteProtocolError,
            httpx.PoolTimeout,
            httpx.NetworkError,
            httpx.TimeoutException,
        ),
    ):
        return True

    # Catch base Python connection errors that may escape httpx wrapping
    # (e.g., raw httpcore / socket errors)
    if isinstance(exc, (ConnectionError, OSError, TimeoutError)):
        return True

    return False


@dataclass
class PatientScenario:
    """Represents a complete patient journey scenario."""

    name: str
    description: str
    patient_profile: dict[str, Any]
    journey_steps: list[dict[str, Any]]
    expected_duration: int
    # Optional enriched clinical context for more realistic simulations.
    # Backward-compatible: scenarios without this field remain valid.
    medical_history: dict[str, Any] = field(default_factory=dict)
    # Bounded stochastic simulation controls.
    simulation_profile: dict[str, Any] = field(default_factory=dict)
    # Optional metadata for negative clinical journeys.
    negative_class: str | None = None
    expected_escalation: str | None = None
    expected_safe_outcome: str | None = None


def create_jwt_token(subject: str = "test-patient-scenario") -> str:
    return mint_jwt(subject, "dev-secret-change-me")


async def make_jsonrpc_call(
    url: str,
    method: str,
    params: dict[str, Any],
    task_id: str,
    *,
    trace_id: str = "",
    step_index: int = 0,
    scenario_name: str = "",
    patient_id: str = "",
    visit_id: str = "",
) -> tuple[dict[str, Any], TraceStepEvent | None]:
    correlation_id = f"corr-{uuid.uuid4()}"
    headers = {
        "Authorization": f"Bearer {create_jwt_token()}",
        "Content-Type": "application/json",
    }
    if trace_id:
        headers["X-Trace-ID"] = trace_id
        headers["X-Correlation-ID"] = correlation_id
    payload = {
        "jsonrpc": "2.0",
        "id": task_id,
        "method": method,
        "params": params,
    }

    rpc_url = url
    if "/rpc/" not in rpc_url and not rpc_url.rstrip("/").endswith("/rpc"):
        rpc_url = f"{rpc_url.rstrip('/')}/rpc"
    print(f"📞 Calling {rpc_url} - Method: {method}")
    timeout = httpx.Timeout(
        connect=ACTIVE_RETRY_CONFIG.connect_timeout_seconds,
        read=ACTIVE_RETRY_CONFIG.read_timeout_seconds,
        write=ACTIVE_RETRY_CONFIG.connect_timeout_seconds,
        pool=ACTIVE_RETRY_CONFIG.connect_timeout_seconds,
    )

    ts_start = datetime.now().astimezone().isoformat()
    start_time = time.perf_counter()
    last_error = "unknown error"
    attempts_made = 0
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            limiter = RPC_ENDPOINT_LIMITERS.get(rpc_url)
            for attempt in range(1, ACTIVE_RETRY_CONFIG.max_rpc_attempts + 1):
                attempts_made = attempt
                try:
                    if limiter is None:
                        response = await client.post(
                            rpc_url,
                            json=payload,
                            headers=headers,
                        )
                    else:
                        async with limiter:
                            response = await client.post(
                                rpc_url,
                                json=payload,
                                headers=headers,
                            )
                    response.raise_for_status()
                    result = response.json()
                    if attempt > 1:
                        print(f"   ✅ Response received (recovered on attempt {attempt})")
                    else:
                        print("   ✅ Response received")
                    ts_end = datetime.now().astimezone().isoformat()
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    step_event = _build_trace_step(
                        trace_id=trace_id,
                        correlation_id=correlation_id,
                        scenario_name=scenario_name,
                        patient_id=patient_id,
                        visit_id=visit_id,
                        agent=task_id.rsplit("-", 2)[-2] if "-" in task_id else method,
                        method=method,
                        step_index=step_index,
                        ts_start=ts_start,
                        ts_end=ts_end,
                        duration_ms=duration_ms,
                        status="final",
                        request=payload,
                        response=result,
                        retry_count=attempts_made - 1,
                        headers=headers,
                    )
                    return result, step_event
                except (Exception, asyncio.CancelledError) as exc:
                    # asyncio.CancelledError is BaseException in Python 3.9+ and can
                    # leak from httpx/httpcore when connect timeouts fire internally.
                    last_error = str(exc) or type(exc).__name__
                    retriable = isinstance(exc, asyncio.CancelledError) or _is_retriable_error(exc)
                    print(
                        "   ❌ Attempt "
                        f"{attempt}/{ACTIVE_RETRY_CONFIG.max_rpc_attempts} failed"
                        f" ({'retriable' if retriable else 'non-retriable'}): {last_error}"
                    )

                    if not retriable:
                        ts_end = datetime.now().astimezone().isoformat()
                        duration_ms = (time.perf_counter() - start_time) * 1000
                        step_event = _build_trace_step(
                            trace_id=trace_id,
                            correlation_id=correlation_id,
                            scenario_name=scenario_name,
                            patient_id=patient_id,
                            visit_id=visit_id,
                            agent=task_id.rsplit("-", 2)[-2] if "-" in task_id else method,
                            method=method,
                            step_index=step_index,
                            ts_start=ts_start,
                            ts_end=ts_end,
                            duration_ms=duration_ms,
                            status="error",
                            request=payload,
                            response={"error": last_error},
                            retry_count=attempts_made - 1,
                            headers=headers,
                            error_message=last_error,
                        )
                        return {"error": last_error, "attempts": attempts_made}, step_event

                    if attempt >= ACTIVE_RETRY_CONFIG.max_rpc_attempts:
                        break

                    elapsed = time.perf_counter() - start_time
                    remaining_budget = ACTIVE_RETRY_CONFIG.max_retry_budget_seconds - elapsed
                    if remaining_budget <= 0:
                        print("   ⏱ Retry budget exhausted for this call")
                        break

                    delay = min(_retry_delay_seconds(attempt), remaining_budget)
                    print(f"   ↻ Retrying in {delay:.2f}s")
                    if delay > 0:
                        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        # httpx/httpcore can leak CancelledError (BaseException in 3.9+)
        # when connect timeouts fire via anyio task groups.
        last_error = "CancelledError (connect timeout)"
        print(
            f"   ❌ Attempt {attempts_made}/{ACTIVE_RETRY_CONFIG.max_rpc_attempts} failed (retriable): {last_error}"
        )

    print("   ❌ Error: All connection attempts failed")
    ts_end = datetime.now().astimezone().isoformat()
    duration_ms = (time.perf_counter() - start_time) * 1000
    step_event = _build_trace_step(
        trace_id=trace_id,
        correlation_id=correlation_id,
        scenario_name=scenario_name,
        patient_id=patient_id,
        visit_id=visit_id,
        agent=task_id.rsplit("-", 2)[-2] if "-" in task_id else method,
        method=method,
        step_index=step_index,
        ts_start=ts_start,
        ts_end=ts_end,
        duration_ms=duration_ms,
        status="error",
        request=payload,
        response={"error": last_error},
        retry_count=attempts_made - 1,
        headers=headers,
        error_message=last_error,
    )
    return {"error": last_error, "attempts": attempts_made}, step_event


def _build_trace_step(
    *,
    trace_id: str,
    correlation_id: str,
    scenario_name: str,
    patient_id: str,
    visit_id: str,
    agent: str,
    method: str,
    step_index: int,
    ts_start: str,
    ts_end: str,
    duration_ms: float,
    status: str,
    request: dict[str, Any],
    response: dict[str, Any],
    retry_count: int,
    headers: dict[str, str],
    error_message: str | None = None,
) -> TraceStepEvent | None:
    """Build a TraceStepEvent with redacted payloads.  Returns None if trace_id is empty."""
    if not trace_id:
        return None
    req_redacted, req_meta = redact_payload({**request, "_headers": headers})
    resp_redacted, resp_meta = redact_payload(response)
    combined_meta = {
        "request": req_meta,
        "response": resp_meta,
    }
    return TraceStepEvent(
        trace_id=trace_id,
        correlation_id=correlation_id,
        scenario_name=scenario_name,
        patient_id=patient_id,
        visit_id=visit_id,
        agent=agent,
        method=method,
        step_index=step_index,
        timestamp_start=ts_start,
        timestamp_end=ts_end,
        duration_ms=round(duration_ms, 2),
        status=status,
        request_redacted=req_redacted,
        response_redacted=resp_redacted,
        redaction_meta=combined_meta,
        retry_count=retry_count,
        error_message=error_message,
    )


def _step(
    agent: str,
    method: str,
    params: dict[str, Any],
    delay: int = 1,
    *,
    handoff_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    step: dict[str, Any] = {
        "agent": agent,
        "method": method,
        "params": params,
        "delay": delay,
    }
    if handoff_policy:
        step["handoff_policy"] = handoff_policy
    return step


def _avatar_consult(
    persona: str,
    chief_complaint: str,
    age: int,
    gender: str,
    urgency: str = "medium",
    *,
    delay: int = 2,
    handoff_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a clinician avatar start_session step."""
    step: dict[str, Any] = {
        "agent": "clinician_avatar",
        "method": "avatar/start_session",
        "params": {
            "patient_case": {
                "chief_complaint": chief_complaint,
                "age": age,
                "gender": gender,
                "urgency": urgency,
            },
            "persona": persona,
        },
        "delay": delay,
    }
    if handoff_policy:
        step["handoff_policy"] = handoff_policy
    return step


def _avatar_msg(
    message: str,
    *,
    delay: int = 2,
    handoff_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a clinician avatar patient_message step."""
    step: dict[str, Any] = {
        "agent": "clinician_avatar",
        "method": "avatar/patient_message",
        "params": {
            "session_id": "$ctx.agent_outputs.clinician_avatar.session_id",
            "message": message,
        },
        "delay": delay,
    }
    if handoff_policy:
        step["handoff_policy"] = handoff_policy
    return step


def _future(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).isoformat()


def _stable_seed(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _default_simulation_profile(name: str) -> dict[str, Any]:
    return {
        "seed": _stable_seed(name),
        "variance_band": "low",
        "allowed_branches": ["nominal", "handoff_delay", "context_gap"],
    }


def _is_transfer_step(step: dict[str, Any]) -> bool:
    agent = str(step.get("agent", "")).strip().lower()
    method = str(step.get("method", "")).strip().lower()
    if agent in {"bed_manager", "discharge", "followup", "coordinator"}:
        return True
    transfer_tokens = ("handoff", "transfer", "admission", "discharge", "followup")
    return any(token in method for token in transfer_tokens)


def _infer_criticality(step: dict[str, Any]) -> str:
    agent = str(step.get("agent", "")).strip().lower()
    if agent in {
        "triage",
        "diagnosis",
        "imaging",
        "pharmacy",
        "bed_manager",
        "discharge",
        "followup",
        "coordinator",
        "primary_care",
        "specialty_care",
        "telehealth",
        "home_visit",
        "ccm",
        "clinician_avatar",
        "transcriber",
        "summariser",
        "ehr_writer",
        "provider_agent",
        "insurer_agent",
        "consent_analyser",
        "hospital_reporter",
        "central_surveillance",
    }:
        return "clinical"
    return "administrative"


def _default_required_handover_fields(step: dict[str, Any]) -> list[str]:
    if not _is_transfer_step(step):
        return []
    return [
        "handover.situation",
        "handover.background",
        "handover.assessment",
        "handover.recommendation",
        "handover.plan",
        "handover.outstanding_tasks",
        "handover.communication_needs",
    ]


def _default_escalation_path(step: dict[str, Any]) -> list[str]:
    agent = str(step.get("agent", "")).strip().lower()
    if agent in {"discharge", "bed_manager"}:
        return ["care_coordinator", "senior_clinician", "hitl_ui"]
    return ["care_coordinator", "hitl_ui"]


def _default_max_wait_seconds(step: dict[str, Any]) -> int:
    agent = str(step.get("agent", "")).strip().lower()
    if agent in {"triage", "diagnosis", "discharge"}:
        return 900
    if _is_transfer_step(step):
        return 1200
    return 600


def _default_safe_fallback_branch(step: dict[str, Any]) -> str | None:
    agent = str(step.get("agent", "")).strip().lower()
    if agent == "discharge":
        return "admit_for_senior_review"
    if agent == "followup":
        return "manual_followup_queue"
    if agent == "imaging":
        return "diagnostic_reassessment"
    return None


def _normalize_handoff_policy(
    step: dict[str, Any],
    predecessor_agent: str | None,
) -> dict[str, Any]:
    policy = step.get("handoff_policy") if isinstance(step.get("handoff_policy"), dict) else {}
    policy = dict(policy)

    # Backward compatibility for legacy field name.
    if "fallback_mode" not in policy and "fallback_action" in policy:
        action = str(policy.get("fallback_action", "")).strip().lower()
        mapping = {"fail": "block_escalate", "stub": "degraded_allow", "skip": "skip"}
        policy["fallback_mode"] = mapping.get(action, "block_escalate")

    policy.setdefault("criticality", _infer_criticality(step))
    policy.setdefault("fallback_mode", "block_escalate")
    policy.setdefault("required_predecessors", [])
    policy.setdefault("optional_predecessors", [])
    policy.setdefault("required_context_keys", [])
    policy.setdefault("required_handover_fields", _default_required_handover_fields(step))
    policy.setdefault("escalation_path", _default_escalation_path(step))
    policy.setdefault("max_wait_seconds", _default_max_wait_seconds(step))
    policy.setdefault("safe_fallback_branch", _default_safe_fallback_branch(step))
    policy.setdefault(
        "guideline_refs",
        [
            "NICE-QS174-Statement4",
            "NICE-NG5",
            "NICE-QS213-Statement5",
            "WHO-Medication-Without-Harm",
        ],
    )

    if (
        predecessor_agent
        and not policy["required_predecessors"]
        and not policy["optional_predecessors"]
    ):
        policy["required_predecessors"] = [predecessor_agent]

    # Only explicitly administrative steps may skip.
    if policy.get("fallback_mode") == "skip" and policy.get("criticality") not in {
        "administrative",
        "admin",
    }:
        policy["fallback_mode"] = "block_escalate"

    return policy


def _apply_transition_ownership(step: dict[str, Any]) -> None:
    params = step.get("params")
    if not isinstance(params, dict):
        return

    if not _is_transfer_step(step):
        return

    agent = str(step.get("agent", "")).strip().lower()
    owner_map = {
        "bed_manager": "admitting_registrar",
        "discharge": "discharging_clinician",
        "followup": "discharge_coordinator",
        "coordinator": "care_coordinator",
    }
    team_map = {
        "bed_manager": "inpatient_team",
        "discharge": "community_care_team",
        "followup": "primary_care_team",
        "coordinator": "multidisciplinary_team",
    }
    care_transition = params.get("care_transition")
    if not isinstance(care_transition, dict):
        care_transition = {}
        params["care_transition"] = care_transition

    care_transition.setdefault("handover_owner", owner_map.get(agent, "care_team"))
    care_transition.setdefault("receiving_team", team_map.get(agent, "receiving_team"))
    care_transition.setdefault("followup_responsibility", "primary_care_team")
    care_transition.setdefault("receiving_provider_notified", True)

    handover = care_transition.get("handover")
    if not isinstance(handover, dict):
        handover = {}
        care_transition["handover"] = handover

    handover.setdefault(
        "situation", str(params.get("symptoms") or params.get("chief_complaint") or "")
    )
    handover.setdefault("background", "Relevant history and context shared.")
    handover.setdefault("assessment", "Clinical assessment documented.")
    handover.setdefault("recommendation", "Proceed with receiving-team plan.")
    handover.setdefault("plan", "Follow local pathway and monitor response.")
    handover.setdefault("outstanding_tasks", ["Confirm plan ownership"])
    handover.setdefault("communication_needs", "No specific communication barriers documented.")


def enrich_scenario_handoff_contracts(scenarios: list[PatientScenario]) -> None:
    """Normalize scenario contracts so each step has explicit safety metadata."""
    for scenario in scenarios:
        profile = _default_simulation_profile(scenario.name)
        for key, value in profile.items():
            scenario.simulation_profile.setdefault(key, value)

        previous_agent: str | None = None
        for step in scenario.journey_steps:
            if not isinstance(step, dict):
                continue
            step["handoff_policy"] = _normalize_handoff_policy(step, previous_agent)
            _apply_transition_ownership(step)
            previous_agent = str(step.get("agent", "")).strip().lower() or previous_agent


def _scenario_simulation_profile(scenario: PatientScenario) -> dict[str, Any]:
    profile = dict(_default_simulation_profile(scenario.name))
    profile.update(dict(getattr(scenario, "simulation_profile", {}) or {}))
    env_seed = os.getenv("HELIXCARE_SIMULATION_SEED", "").strip()
    if env_seed:
        try:
            profile["seed"] = int(env_seed)
        except Exception:
            profile["seed"] = _stable_seed(env_seed)
    env_band = os.getenv("HELIXCARE_VARIANCE_BAND", "").strip().lower()
    if env_band in {"low", "medium", "high"}:
        profile["variance_band"] = env_band
    return profile


def _branch_probability(variance_band: str) -> float:
    band = variance_band.strip().lower()
    if band == "high":
        return 0.35
    if band == "medium":
        return 0.2
    return 0.08


def _choose_simulation_branch(
    *,
    rng: random.Random,
    profile: dict[str, Any],
) -> str:
    branches = list(profile.get("allowed_branches") or ["nominal"])
    if "nominal" not in branches:
        branches.insert(0, "nominal")
    if len(branches) == 1:
        return "nominal"

    p_non_nominal = _branch_probability(str(profile.get("variance_band", "low")))
    if rng.random() >= p_non_nominal:
        return "nominal"

    non_nominal = [b for b in branches if b != "nominal"]
    return str(rng.choice(non_nominal)) if non_nominal else "nominal"


def _is_ai_agent_driven_enabled() -> bool:
    return os.getenv("HELIXCARE_AI_AGENT_DRIVEN", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _ai_agent_driven_intensity() -> str:
    value = os.getenv("HELIXCARE_AI_AGENT_DRIVEN_INTENSITY", "high").strip().lower()
    return value if value in {"low", "medium", "high"} else "high"


def _agent_driven_profile(base_profile: dict[str, Any], intensity: str) -> dict[str, Any]:
    profile = dict(base_profile or {})
    profile["variance_band"] = "medium" if intensity == "low" else intensity

    branches = list(profile.get("allowed_branches") or ["nominal"])
    for branch in [
        "triage_escalation",
        "safety_fallback",
        "parallel_handoff",
        "delayed_data",
    ]:
        if branch not in branches:
            branches.append(branch)
    profile["allowed_branches"] = branches
    return profile


SCENARIOS = [
    PatientScenario(
        name="primary_care_outpatient_in_person",
        description="In-person primary care visit with assessment, treatment, and checkout.",
        patient_profile={
            "age": 47,
            "gender": "female",
            "chief_complaint": "Fatigue and elevated blood pressure follow-up",
            "urgency": "medium",
        },
        medical_history={
            "past_medical_history": [
                "Type 2 diabetes",
                "Hypertension",
                "Iron deficiency anemia (history)",
            ],
            "medications": ["Metformin 1000 mg BID", "Lisinopril 10 mg daily"],
            "allergies": ["No known drug allergies"],
            "social_history": {
                "tobacco": "never",
                "alcohol": "occasional",
                "occupation": "Administrative assistant",
                "exercise": "limited due to fatigue",
            },
            "family_history": ["Mother with hypertension", "Father with type 2 diabetes"],
            "review_of_systems": {
                "constitutional": "Fatigue over 6 weeks, no fevers",
                "neurologic": "Intermittent headaches, no focal deficits",
            },
            "vital_signs": {
                "blood_pressure": "152/92",
                "heart_rate": 82,
                "respiratory_rate": 16,
                "oxygen_saturation": 98,
                "temperature_c": 36.7,
            },
        },
        journey_steps=[
            _step(
                "primary_care",
                "primary_care/manage_visit",
                {"visit_mode": "in_person", "complaint": "fatigue and hypertension follow-up"},
            ),
            _avatar_consult(
                "senior_internist",
                "Fatigue and elevated blood pressure follow-up",
                47,
                "female",
                "medium",
                handoff_policy={
                    "required_predecessors": ["primary_care"],
                    "clinical_rationale": "Internist reviews chief complaint after initial intake",
                },
            ),
            _avatar_msg(
                "I've been so tired the last six weeks. Even small tasks at work exhaust me, and my headaches are getting worse.",
                handoff_policy={
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Patient describes symptom trajectory during interview",
                },
            ),
            _step(
                "diagnosis",
                "tasks/sendSubscribe",
                {
                    "symptoms": "fatigue, headaches",
                    "differential_diagnosis": ["Hypertension", "Anemia", "Thyroid dysfunction"],
                },
                2,
                handoff_policy={
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Diagnosis follows clinician interview findings",
                },
            ),
            _step(
                "pharmacy",
                "pharmacy/recommend",
                {
                    "task": {
                        "med_plan": ["Lisinopril"],
                        "allergies": [],
                        "current_medications": ["Metformin"],
                    }
                },
                handoff_policy={
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": "Medication adjustment based on diagnostic assessment",
                },
            ),
            _step(
                "followup",
                "tasks/sendSubscribe",
                {
                    "followup_schedule": [
                        {
                            "type": "primary_care",
                            "when": _future(30),
                            "purpose": "BP and lab review",
                        }
                    ]
                },
                1,
                handoff_policy={
                    "required_predecessors": ["diagnosis"],
                    "optional_predecessors": ["pharmacy"],
                    "clinical_rationale": "Follow-up scheduled after diagnosis and treatment plan",
                },
            ),
        ],
        expected_duration=16,
    ),
    PatientScenario(
        name="specialty_outpatient_clinic",
        description="Specialty clinic workflow with referral triage and diagnostics.",
        patient_profile={
            "age": 61,
            "gender": "male",
            "chief_complaint": "Progressive exertional chest discomfort",
            "urgency": "high",
        },
        medical_history={
            "past_medical_history": ["Hypertension", "Hyperlipidemia", "GERD"],
            "medications": ["Aspirin 81 mg daily", "Atorvastatin 20 mg nightly"],
            "allergies": ["No known drug allergies"],
            "social_history": {
                "tobacco": "former smoker (15 pack-years)",
                "alcohol": "occasional",
                "activity": "reduced exertional tolerance over 2 months",
            },
            "family_history": ["Brother with CAD requiring PCI"],
            "review_of_systems": {
                "cardiac": "Exertional pressure-like chest discomfort relieved by rest",
                "respiratory": "No rest dyspnea, no hemoptysis",
            },
            "vital_signs": {
                "blood_pressure": "146/88",
                "heart_rate": 86,
                "respiratory_rate": 18,
                "oxygen_saturation": 97,
                "temperature_c": 36.6,
            },
        },
        journey_steps=[
            _step(
                "specialty_care",
                "specialty_care/manage_referral",
                {"specialty": "cardiology", "reason": "exertional angina assessment"},
            ),
            _avatar_consult(
                "senior_cardiologist",
                "Progressive exertional chest discomfort",
                61,
                "male",
                "high",
                handoff_policy={
                    "required_predecessors": ["specialty_care"],
                    "clinical_rationale": "Cardiologist interviews patient after referral intake",
                },
            ),
            _avatar_msg(
                "The pressure comes on when I walk uphill or carry groceries. It eases after I rest for a few minutes. My brother had the same thing before his stents.",
                handoff_policy={
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Patient provides exertional symptom history",
                },
            ),
            _step(
                "diagnosis",
                "tasks/sendSubscribe",
                {
                    "symptoms": "exertional chest discomfort",
                    "differential_diagnosis": ["Stable angina", "GERD", "Aortic stenosis"],
                },
                2,
                handoff_policy={
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Diagnosis informed by cardiologist interview findings",
                },
            ),
            _step(
                "imaging",
                "tasks/sendSubscribe",
                {
                    "orders": [
                        {"type": "ecg", "priority": "urgent", "indication": "cardiac rhythm"},
                        {
                            "type": "stress_echo",
                            "priority": "routine",
                            "indication": "ischemia workup",
                        },
                    ]
                },
                2,
                handoff_policy={
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": "Imaging ordered based on diagnostic assessment",
                },
            ),
            _step(
                "coordinator",
                "tasks/sendSubscribe",
                {
                    "task": {
                        "journey_type": "specialty_outpatient",
                        "coordination_tasks": [
                            "Prior authorization",
                            "Procedure scheduling",
                            "PCP communication",
                        ],
                    }
                },
                2,
                handoff_policy={
                    "required_predecessors": ["diagnosis"],
                    "optional_predecessors": ["imaging"],
                    "clinical_rationale": "Care coordination after diagnostic workup initiated",
                },
            ),
        ],
        expected_duration=18,
    ),
    PatientScenario(
        name="telehealth_video_consult",
        description="Video telehealth consult with identity/location verification and remote plan.",
        patient_profile={
            "age": 35,
            "gender": "female",
            "chief_complaint": "Migraine follow-up",
            "urgency": "low",
        },
        medical_history={
            "past_medical_history": ["Migraine without aura", "Generalized anxiety disorder"],
            "medications": ["Sumatriptan 50 mg PRN", "Sertraline 50 mg daily"],
            "allergies": ["No known drug allergies"],
            "social_history": {
                "tobacco": "never",
                "alcohol": "occasional",
                "occupation": "Software engineer",
                "sleep": "5-6 hours/night during work weeks",
            },
            "family_history": ["Mother with migraine"],
            "review_of_systems": {
                "neurologic": "Photophobia and pulsatile unilateral headaches; no focal deficits",
                "constitutional": "No fever, no weight loss",
            },
            "vital_signs": {
                "blood_pressure": "124/78",
                "heart_rate": 74,
                "respiratory_rate": 16,
                "oxygen_saturation": 99,
                "temperature_c": 36.7,
            },
        },
        journey_steps=[
            _step(
                "telehealth",
                "telehealth/consult",
                {"modality": "video", "location_verified": True, "consent_documented": True},
            ),
            _avatar_consult(
                "neurologist",
                "Migraine follow-up",
                35,
                "female",
                "low",
                handoff_policy={
                    "required_predecessors": ["telehealth"],
                    "clinical_rationale": "Neurologist conducts structured migraine review via video",
                },
            ),
            _avatar_msg(
                "The migraines are still happening twice a week. Sumatriptan helps but I'm worried about using it too often. My sleep has been terrible with the project deadlines.",
                handoff_policy={
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Patient reports frequency and medication concerns",
                },
            ),
            _step(
                "diagnosis",
                "tasks/sendSubscribe",
                {
                    "symptoms": "recurrent migraines, photophobia",
                    "differential_diagnosis": ["Migraine", "Medication overuse headache"],
                },
                2,
                handoff_policy={
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Diagnosis refined by clinician consultation findings",
                },
            ),
            _step(
                "pharmacy",
                "pharmacy/recommend",
                {"task": {"med_plan": ["Ibuprofen"], "allergies": [], "current_medications": []}},
                1,
                handoff_policy={
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": "Medication adjusted based on diagnostic assessment",
                },
            ),
            _step(
                "followup",
                "tasks/sendSubscribe",
                {
                    "followup_schedule": [
                        {
                            "type": "telehealth",
                            "when": _future(14),
                            "purpose": "response to treatment",
                        }
                    ]
                },
                1,
                handoff_policy={
                    "required_predecessors": ["diagnosis"],
                    "optional_predecessors": ["pharmacy"],
                    "clinical_rationale": "Follow-up to assess treatment response",
                },
            ),
        ],
        expected_duration=14,
    ),
    PatientScenario(
        name="telehealth_audio_only_followup",
        description="Audio-only telehealth follow-up with escalation guardrails.",
        patient_profile={
            "age": 73,
            "gender": "male",
            "chief_complaint": "Medication side-effect review",
            "urgency": "low",
        },
        medical_history={
            "past_medical_history": ["Hypertension", "Stage 3 CKD", "Osteoarthritis"],
            "medications": ["Lisinopril 10 mg daily", "Ibuprofen 400 mg PRN"],
            "allergies": ["Sulfa (rash)"],
            "social_history": {
                "tobacco": "never",
                "alcohol": "none",
                "living_situation": "lives with spouse",
            },
            "family_history": ["Mother with hypertension"],
            "review_of_systems": {
                "neurologic": "Intermittent dizziness after medication change",
                "cardiovascular": "No syncope, no chest pain",
            },
            "vital_signs": {
                "blood_pressure": "118/66",
                "heart_rate": 72,
                "respiratory_rate": 16,
                "oxygen_saturation": 98,
                "temperature_c": 36.5,
            },
        },
        journey_steps=[
            _step(
                "telehealth",
                "telehealth/consult",
                {"modality": "audio_only", "location_verified": True, "consent_documented": True},
            ),
            _avatar_consult(
                "senior_internist",
                "Medication side-effect review",
                73,
                "male",
                "low",
                handoff_policy={
                    "required_predecessors": ["telehealth"],
                    "clinical_rationale": "Internist reviews medication side-effects via audio",
                },
            ),
            _avatar_msg(
                "I've been feeling dizzy when I stand up since my doctor changed my blood pressure medication last month. It happens mostly in the morning.",
                handoff_policy={
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Patient describes orthostatic symptoms timeline",
                },
            ),
            _step(
                "primary_care",
                "primary_care/manage_visit",
                {"visit_mode": "audio_only", "complaint": "dizziness after medication change"},
                handoff_policy={
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "PCP assessment informed by avatar interview findings",
                },
            ),
            _step(
                "pharmacy",
                "pharmacy/check_interactions",
                {"drugs": ["Lisinopril", "Ibuprofen"]},
                1,
                handoff_policy={
                    "required_predecessors": ["primary_care"],
                    "clinical_rationale": "Drug interaction check after PCP dosage review",
                },
            ),
            _step(
                "followup",
                "tasks/sendSubscribe",
                {
                    "followup_schedule": [
                        {
                            "type": "in_person_primary_care",
                            "when": _future(7),
                            "purpose": "orthostatic vitals and exam",
                        }
                    ]
                },
                1,
                handoff_policy={
                    "required_predecessors": ["primary_care"],
                    "optional_predecessors": ["pharmacy"],
                    "clinical_rationale": "In-person follow-up for orthostatic assessment",
                },
            ),
        ],
        expected_duration=13,
    ),
    PatientScenario(
        name="home_visit_house_call",
        description="Home-based primary care visit including environment and safety assessment.",
        patient_profile={
            "age": 84,
            "gender": "female",
            "chief_complaint": "Frailty and recurrent falls",
            "urgency": "medium",
        },
        medical_history={
            "past_medical_history": [
                "Atrial fibrillation",
                "Osteoporosis",
                "Mild cognitive impairment",
            ],
            "medications": ["Warfarin 5 mg daily", "Vitamin D3 1000 IU daily"],
            "allergies": ["Codeine (nausea)"],
            "social_history": {
                "living_situation": "Lives alone with daytime caregiver support",
                "mobility": "Uses walker",
                "home_risks": ["Loose rugs", "Poor bathroom grab-bar support"],
            },
            "family_history": ["Daughter with osteoporosis"],
            "review_of_systems": {
                "musculoskeletal": "Gait instability and lower-extremity weakness",
                "neurologic": "No recent syncope, intermittent confusion at night",
            },
            "vital_signs": {
                "blood_pressure": "134/74",
                "heart_rate": 78,
                "respiratory_rate": 18,
                "oxygen_saturation": 97,
                "temperature_c": 36.4,
            },
        },
        journey_steps=[
            _step(
                "home_visit",
                "home_visit/dispatch",
                {"home_safety_screen": True, "caregiver_present": True},
            ),
            _avatar_consult(
                "geriatrician",
                "Frailty and recurrent falls",
                84,
                "female",
                "medium",
                handoff_policy={
                    "required_predecessors": ["home_visit"],
                    "clinical_rationale": "Geriatrician assesses fall risk and cognitive status",
                },
            ),
            _avatar_msg(
                "I fell again last Tuesday getting out of bed. My legs just gave out. My daughter says I seem more confused at night lately.",
                handoff_policy={
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Patient reports falls and nighttime confusion",
                },
            ),
            _step(
                "primary_care",
                "primary_care/manage_visit",
                {"visit_mode": "home", "complaint": "falls and mobility decline"},
                2,
                handoff_policy={
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "PCP assessment informed by geriatric consultation",
                },
            ),
            _step(
                "pharmacy",
                "pharmacy/recommend",
                {
                    "task": {
                        "med_plan": ["Acetaminophen"],
                        "allergies": [],
                        "current_medications": ["Warfarin"],
                    }
                },
                1,
                handoff_policy={
                    "required_predecessors": ["primary_care"],
                    "clinical_rationale": "Pain management avoiding fall-risk medications",
                },
            ),
            _step(
                "coordinator",
                "tasks/sendSubscribe",
                {
                    "task": {
                        "journey_type": "home_visit",
                        "coordination_tasks": [
                            "Home health referral",
                            "DME order",
                            "Falls prevention education",
                        ],
                    }
                },
                2,
                handoff_policy={
                    "required_predecessors": ["primary_care"],
                    "optional_predecessors": ["pharmacy"],
                    "clinical_rationale": "Care coordination for home safety and DME",
                },
            ),
        ],
        expected_duration=19,
    ),
    PatientScenario(
        name="chronic_care_management_monthly",
        description="Longitudinal CCM monthly cycle with care-plan update and coordination.",
        patient_profile={
            "age": 69,
            "gender": "male",
            "chief_complaint": "CCM monthly review for diabetes and CHF",
            "urgency": "low",
        },
        medical_history={
            "past_medical_history": [
                "Type 2 diabetes",
                "Congestive heart failure (HFrEF)",
                "Chronic kidney disease stage 2",
            ],
            "medications": [
                "Metformin 1000 mg BID",
                "Lisinopril 20 mg daily",
                "Aspirin 81 mg daily",
                "Furosemide 20 mg daily",
            ],
            "allergies": ["No known drug allergies"],
            "social_history": {
                "diet": "Inconsistent low-sodium adherence",
                "activity": "Walks 10-15 minutes/day",
                "self_monitoring": "Intermittent glucose and weight logging",
            },
            "family_history": ["Brother with heart failure"],
            "review_of_systems": {
                "cardiac": "Mild exertional dyspnea, occasional ankle edema",
                "endocrine": "Variable fasting glucose control",
            },
            "vital_signs": {
                "blood_pressure": "140/84",
                "heart_rate": 80,
                "respiratory_rate": 18,
                "oxygen_saturation": 96,
                "temperature_c": 36.8,
            },
        },
        journey_steps=[
            _step(
                "ccm",
                "ccm/monthly_review",
                {"conditions": ["Diabetes", "CHF"], "monthly_minutes": 25},
            ),
            _avatar_consult(
                "senior_internist",
                "CCM monthly review for diabetes and CHF",
                69,
                "male",
                "low",
                handoff_policy={
                    "required_predecessors": ["ccm"],
                    "clinical_rationale": "Internist check-in after care-plan metrics review",
                },
            ),
            _avatar_msg(
                "My ankles have been swelling a bit more this week. I've been trying to cut back on salt but it's hard with the processed food my wife buys.",
                handoff_policy={
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Patient reports fluid retention and dietary challenges",
                },
            ),
            _step(
                "primary_care",
                "primary_care/manage_visit",
                {"visit_mode": "care_management", "complaint": "goal and plan review"},
                1,
                handoff_policy={
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "PCP adjusts care plan based on avatar interview",
                },
            ),
            _step(
                "followup",
                "tasks/sendSubscribe",
                {
                    "followup_schedule": [
                        {
                            "type": "ccm_touchpoint",
                            "when": _future(30),
                            "purpose": "next monthly review",
                        }
                    ]
                },
                1,
                handoff_policy={
                    "required_predecessors": ["primary_care"],
                    "clinical_rationale": "Schedule next monthly CCM review cycle",
                },
            ),
            _step(
                "pharmacy",
                "pharmacy/check_interactions",
                {"drugs": ["Metformin", "Lisinopril", "Aspirin"]},
                1,
                handoff_policy={
                    "required_predecessors": ["primary_care"],
                    "clinical_rationale": "Verify drug interactions after plan adjustments",
                },
            ),
        ],
        expected_duration=15,
    ),
    PatientScenario(
        name="emergency_department_treat_and_release",
        description="ED flow resulting in treatment and safe discharge.",
        patient_profile={
            "age": 29,
            "gender": "male",
            "chief_complaint": "Acute asthma exacerbation",
            "urgency": "high",
        },
        medical_history={
            "past_medical_history": ["Asthma (moderate persistent)", "Allergic rhinitis"],
            "medications": ["Albuterol inhaler PRN", "Budesonide-formoterol inhaler BID"],
            "allergies": ["Cats", "Dust mites"],
            "social_history": {
                "tobacco": "never",
                "alcohol": "social",
                "trigger_exposures": ["Cold air", "Recent viral URI", "Missed controller doses"],
            },
            "family_history": ["Sibling with asthma"],
            "review_of_systems": {
                "respiratory": "Wheeze, chest tightness, dyspnea; no hemoptysis",
                "cardiac": "No exertional chest pressure",
            },
            "vital_signs": {
                "blood_pressure": "138/86",
                "heart_rate": 116,
                "respiratory_rate": 28,
                "oxygen_saturation": 92,
                "temperature_c": 37.1,
            },
        },
        journey_steps=[
            _step(
                "triage",
                "tasks/sendSubscribe",
                {
                    "symptoms": "wheezing and dyspnea",
                    "chief_complaint": "asthma flare",
                    "arrival_time": datetime.now().isoformat(),
                },
            ),
            _avatar_consult(
                "emergency_physician",
                "Acute asthma exacerbation",
                29,
                "male",
                "high",
                handoff_policy={
                    "required_predecessors": ["triage"],
                    "clinical_rationale": "EM physician assesses severity after triage",
                },
            ),
            _avatar_msg(
                "I ran out of my maintenance inhaler last week and caught a cold. The wheezing started yesterday and got really bad this morning. I can barely finish a sentence.",
                handoff_policy={
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Patient describes trigger and severity progression",
                },
            ),
            _step(
                "diagnosis",
                "tasks/sendSubscribe",
                {
                    "symptoms": "wheezing and dyspnea",
                    "differential_diagnosis": ["Asthma exacerbation", "Pneumonia", "Pneumothorax"],
                },
                2,
                handoff_policy={
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Diagnosis informed by EM physician interview",
                },
            ),
            _step(
                "imaging",
                "tasks/sendSubscribe",
                {
                    "orders": [
                        {
                            "type": "chest_xray",
                            "priority": "urgent",
                            "indication": "rule out alternative pathology",
                        }
                    ]
                },
                2,
                handoff_policy={
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": "CXR ordered to exclude pneumothorax/pneumonia",
                },
            ),
            _step(
                "pharmacy",
                "tasks/sendSubscribe",
                {"task": {"med_plan": ["Albuterol", "Prednisone"], "allergies": []}},
                1,
                handoff_policy={
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": "Bronchodilator and steroid therapy based on diagnosis",
                },
            ),
            _step(
                "discharge",
                "tasks/sendSubscribe",
                {
                    "task": {
                        "discharge_diagnosis": "Asthma exacerbation",
                        "discharge_disposition": "home",
                    }
                },
                1,
                handoff_policy={
                    "required_predecessors": ["pharmacy"],
                    "optional_predecessors": ["imaging"],
                    "clinical_rationale": "Discharge after treatment response and CXR clear",
                },
            ),
            _step(
                "followup",
                "tasks/sendSubscribe",
                {
                    "followup_schedule": [
                        {"type": "primary_care", "when": _future(3), "purpose": "post-ED check"}
                    ]
                },
                1,
                handoff_policy={
                    "required_predecessors": ["discharge"],
                    "clinical_rationale": "Early PCP follow-up after ED discharge",
                },
            ),
        ],
        expected_duration=20,
    ),
    PatientScenario(
        name="emergency_department_to_inpatient_admission",
        description="ED flow that escalates to inpatient admission.",
        patient_profile={
            "age": 57,
            "gender": "female",
            "chief_complaint": "Chest pain and diaphoresis",
            "urgency": "critical",
        },
        medical_history={
            "past_medical_history": ["Hypertension", "Hyperlipidemia", "Type 2 diabetes"],
            "medications": [
                "Lisinopril 20 mg daily",
                "Atorvastatin 40 mg nightly",
                "Metformin 1000 mg BID",
            ],
            "allergies": ["Penicillin (rash)"],
            "social_history": {
                "tobacco": "former smoker (20 pack-years)",
                "alcohol": "rare",
                "exercise_tolerance": "decreased over past month",
            },
            "family_history": ["Father with MI at 59"],
            "review_of_systems": {
                "cardiac": "Substernal pressure radiating to left arm with diaphoresis",
                "respiratory": "Mild dyspnea",
                "gi": "Nausea present",
            },
            "vital_signs": {
                "blood_pressure": "168/98",
                "heart_rate": 112,
                "respiratory_rate": 24,
                "oxygen_saturation": 94,
                "temperature_c": 36.8,
            },
        },
        journey_steps=[
            _step(
                "triage",
                "tasks/sendSubscribe",
                {
                    "symptoms": "severe chest pain",
                    "chief_complaint": "possible ACS",
                    "arrival_time": datetime.now().isoformat(),
                },
            ),
            _avatar_consult(
                "emergency_physician",
                "Chest pain and diaphoresis",
                57,
                "female",
                "critical",
                handoff_policy={
                    "required_predecessors": ["triage"],
                    "clinical_rationale": "EM physician rapid assessment of possible ACS",
                },
            ),
            _avatar_msg(
                "The pain came on suddenly about two hours ago while I was at work. It's a heavy pressure right in my chest going down my left arm. I'm sweating and feel nauseous.",
                handoff_policy={
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Patient describes acute onset and radiation pattern",
                },
            ),
            _step(
                "diagnosis",
                "tasks/sendSubscribe",
                {
                    "symptoms": "chest pain and dyspnea",
                    "differential_diagnosis": [
                        "Acute coronary syndrome",
                        "PE",
                        "Aortic dissection",
                    ],
                },
                2,
                handoff_policy={
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Urgent differential guided by EM physician assessment",
                },
            ),
            _step(
                "imaging",
                "tasks/sendSubscribe",
                {
                    "orders": [
                        {"type": "ecg", "priority": "emergent", "indication": "ST changes"},
                        {
                            "type": "chest_xray",
                            "priority": "urgent",
                            "indication": "alternate diagnosis",
                        },
                    ]
                },
                2,
                handoff_policy={
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": "Emergent imaging for suspected ACS",
                },
            ),
            _step(
                "bed_manager",
                "tasks/sendSubscribe",
                {
                    "task": {
                        "admission_type": "emergency",
                        "required_monitoring": "telemetry",
                        "estimated_los": "2-4 days",
                    }
                },
                1,
                handoff_policy={
                    "required_predecessors": ["diagnosis"],
                    "optional_predecessors": ["imaging"],
                    "clinical_rationale": "Telemetry admission for cardiac monitoring",
                },
            ),
            _step(
                "coordinator",
                "tasks/sendSubscribe",
                {
                    "task": {
                        "journey_type": "ed_to_inpatient",
                        "coordination_tasks": ["Cardiology consult", "Inpatient handoff"],
                    }
                },
                1,
                handoff_policy={
                    "required_predecessors": ["bed_manager"],
                    "clinical_rationale": "Cardiology consult and inpatient handoff after admission",
                },
            ),
        ],
        expected_duration=18,
    ),
    PatientScenario(
        name="inpatient_admission_and_daily_rounds",
        description="Inpatient episode focusing on admission, medication safety, and daily review.",
        patient_profile={
            "age": 72,
            "gender": "male",
            "chief_complaint": "Community acquired pneumonia with hypoxia",
            "urgency": "high",
        },
        medical_history={
            "past_medical_history": ["COPD", "Hypertension", "Chronic tobacco exposure"],
            "medications": [
                "Tiotropium inhaler daily",
                "Amlodipine 5 mg daily",
                "Albuterol inhaler PRN",
            ],
            "allergies": ["No known drug allergies"],
            "social_history": {
                "tobacco": "former smoker (40 pack-years)",
                "living_situation": "Lives with spouse",
                "recent_exposure": "Grandchild with respiratory infection",
            },
            "family_history": ["Father with COPD"],
            "review_of_systems": {
                "respiratory": "Productive cough, pleuritic chest discomfort, dyspnea",
                "constitutional": "Fever and fatigue",
            },
            "vital_signs": {
                "blood_pressure": "128/72",
                "heart_rate": 102,
                "respiratory_rate": 26,
                "oxygen_saturation": 88,
                "temperature_c": 38.7,
            },
        },
        journey_steps=[
            _step(
                "bed_manager",
                "admission/assign_bed",
                {"task": {"unit_pref": "Ward", "decision": "admit"}},
            ),
            _avatar_consult(
                "attending_pulmonologist",
                "Community acquired pneumonia with hypoxia",
                72,
                "male",
                "high",
                handoff_policy={
                    "required_predecessors": ["bed_manager"],
                    "clinical_rationale": "Attending evaluates patient on admission to ward",
                },
            ),
            _avatar_msg(
                "I started coughing about five days ago after my grandchild was sick. It got worse and now I can barely breathe. There's some yellowish sputum.",
                handoff_policy={
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Patient describes symptom onset and respiratory status",
                },
            ),
            _step(
                "pharmacy",
                "tasks/sendSubscribe",
                {"task": {"med_plan": ["Amoxicillin", "Oxygen"], "allergies": []}},
                1,
                handoff_policy={
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Antibiotic and supplemental O2 per attending assessment",
                },
            ),
            _step(
                "coordinator",
                "tasks/sendSubscribe",
                {
                    "task": {
                        "journey_type": "inpatient_stay",
                        "coordination_tasks": ["Daily rounds", "Consult sync", "Care-plan update"],
                    }
                },
                2,
                handoff_policy={
                    "required_predecessors": ["pharmacy"],
                    "clinical_rationale": "Care coordination after admission orders placed",
                },
            ),
            _step(
                "ccm",
                "ccm/monthly_review",
                {"conditions": ["COPD"], "monthly_minutes": 20},
                1,
                handoff_policy={
                    "required_predecessors": ["coordinator"],
                    "clinical_rationale": "CCM review for chronic COPD management during stay",
                },
            ),
        ],
        expected_duration=16,
    ),
    PatientScenario(
        name="inpatient_discharge_transition",
        description="Discharge and transition-of-care workflow to outpatient follow-up.",
        patient_profile={
            "age": 66,
            "gender": "female",
            "chief_complaint": "Discharge readiness after CHF admission",
            "urgency": "medium",
        },
        medical_history={
            "past_medical_history": [
                "Congestive heart failure",
                "Hypertension",
                "Coronary artery disease",
            ],
            "medications": [
                "Lisinopril 20 mg daily",
                "Aspirin 81 mg daily",
                "Furosemide 40 mg daily",
            ],
            "allergies": ["Ibuprofen (fluid retention)"],
            "social_history": {
                "diet": "High sodium prior to admission; now educated on restriction",
                "support": "Lives with partner who assists medication management",
                "self_monitoring": "Agrees to daily weight logs",
            },
            "family_history": ["Mother with heart failure"],
            "review_of_systems": {
                "cardiac": "Improved dyspnea and edema compared with admission",
                "constitutional": "No fever; appetite improving",
            },
            "vital_signs": {
                "blood_pressure": "122/70",
                "heart_rate": 76,
                "respiratory_rate": 18,
                "oxygen_saturation": 97,
                "temperature_c": 36.6,
            },
        },
        journey_steps=[
            _avatar_consult(
                "attending_cardiologist",
                "Discharge readiness after CHF admission",
                66,
                "female",
                "medium",
                handoff_policy={
                    "clinical_rationale": "Cardiologist reviews discharge readiness with patient",
                },
            ),
            _avatar_msg(
                "I'm breathing much better now and the swelling in my legs went down. My partner is ready to help me with the daily weight checks at home.",
                handoff_policy={
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Patient confirms symptom improvement and home support",
                },
            ),
            _step(
                "discharge",
                "tasks/sendSubscribe",
                {
                    "task": {
                        "discharge_diagnosis": "Heart failure exacerbation",
                        "discharge_disposition": "home",
                        "followup_instructions": ["Daily weights", "Low sodium diet"],
                    }
                },
                handoff_policy={
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Discharge planned after cardiologist confirms readiness",
                },
            ),
            _step(
                "pharmacy",
                "pharmacy/recommend",
                {
                    "task": {
                        "med_plan": ["Lisinopril", "Aspirin"],
                        "allergies": [],
                        "current_medications": ["Ibuprofen"],
                    }
                },
                1,
                handoff_policy={
                    "required_predecessors": ["discharge"],
                    "clinical_rationale": "Discharge medication reconciliation",
                },
            ),
            _step(
                "followup",
                "tasks/sendSubscribe",
                {
                    "followup_schedule": [
                        {
                            "type": "cardiology",
                            "when": _future(7),
                            "purpose": "post-discharge visit",
                        },
                        {
                            "type": "primary_care",
                            "when": _future(14),
                            "purpose": "transition of care",
                        },
                    ]
                },
                1,
                handoff_policy={
                    "required_predecessors": ["discharge"],
                    "optional_predecessors": ["pharmacy"],
                    "clinical_rationale": "Follow-up scheduling after discharge orders finalized",
                },
            ),
            _step(
                "ccm",
                "ccm/monthly_review",
                {"conditions": ["CHF"], "monthly_minutes": 22},
                1,
                handoff_policy={
                    "required_predecessors": ["discharge"],
                    "clinical_rationale": "CCM enrollment for transition of care monitoring",
                },
            ),
        ],
        expected_duration=15,
    ),
]

enrich_scenario_handoff_contracts(SCENARIOS)


def _load_additional_scenarios() -> list[PatientScenario]:
    """Lazily load additive variants to avoid eager circular imports."""
    try:
        from additional_scenarios import ADDITIONAL_SCENARIOS

        loaded = list(ADDITIONAL_SCENARIOS)
        enrich_scenario_handoff_contracts(loaded)
        return loaded
    except Exception:
        try:
            from tools.additional_scenarios import ADDITIONAL_SCENARIOS

            loaded = list(ADDITIONAL_SCENARIOS)
            enrich_scenario_handoff_contracts(loaded)
            return loaded
        except Exception:
            return []


def _load_clinical_negative_scenarios() -> list[PatientScenario]:
    """Load explicit clinical-negative handoff scenarios (optional suite)."""
    try:
        from clinical_negative_scenarios import CLINICAL_NEGATIVE_SCENARIOS

        loaded = list(CLINICAL_NEGATIVE_SCENARIOS)
        enrich_scenario_handoff_contracts(loaded)
        return loaded
    except Exception:
        try:
            from tools.clinical_negative_scenarios import \
                CLINICAL_NEGATIVE_SCENARIOS

            loaded = list(CLINICAL_NEGATIVE_SCENARIOS)
            enrich_scenario_handoff_contracts(loaded)
            return loaded
        except Exception:
            return []


def _load_representative_scenarios() -> list[PatientScenario]:
    """Load expanded representative journeys (positive + clinical negatives)."""
    try:
        from representative_scenarios import REPRESENTATIVE_SCENARIOS

        loaded = list(REPRESENTATIVE_SCENARIOS)
        enrich_scenario_handoff_contracts(loaded)
        return loaded
    except Exception:
        try:
            from tools.representative_scenarios import REPRESENTATIVE_SCENARIOS

            loaded = list(REPRESENTATIVE_SCENARIOS)
            enrich_scenario_handoff_contracts(loaded)
            return loaded
        except Exception:
            return []


def _resolve_context_template(value: Any, clinical_context: dict[str, Any]) -> Any:
    """Resolve $ctx.<dot.path> references in scenario step params."""
    if isinstance(value, dict):
        return {k: _resolve_context_template(v, clinical_context) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_context_template(v, clinical_context) for v in value]
    if not isinstance(value, str):
        return value
    if not value.startswith("$ctx."):
        return value

    path = value[len("$ctx.") :].split(".")
    cursor: Any = clinical_context
    for segment in path:
        if isinstance(cursor, dict) and segment in cursor:
            cursor = cursor[segment]
            continue
        return value
    return cursor


TRACE_SINK_URL = os.getenv("TRACE_SINK_URL", "http://localhost:8099")


def _scenario_display_title(name: str) -> str:
    """Return a user-facing scenario title without changing internal IDs."""
    role_title_overrides = {
        "clinician_avatar_consultation": "senior_clinician_consultation",
        "clinician_avatar_uk_gp_consultation": "gp_uk_consultation",
        "clinician_avatar_usa_attending_acs": "attending_physician_usa_acs",
        "clinician_avatar_kenya_medical_officer": "medical_officer_kenya_consultation",
        "clinician_avatar_telehealth_uk_followup": "telehealth_clinician_uk_followup",
        "clinician_avatar_psychiatrist_mental_health": "psychiatrist_mental_health_consultation",
    }
    if name in role_title_overrides:
        return role_title_overrides[name]
    return name.replace("avatar", "clinician")


def _agent_display_label(agent_alias: str) -> str:
    """Return user-facing agent labels without avatar wording."""
    alias = str(agent_alias or "").strip().lower()
    role_overrides = {
        "clinician_avatar": "consulting_clinician",
    }
    return role_overrides.get(alias, alias).upper()


async def _post_trace_run(trace_run: TraceRun) -> None:
    """POST completed TraceRun to Command Centre (best-effort)."""
    url = f"{TRACE_SINK_URL.rstrip('/')}/api/traces"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            resp = await client.post(url, json=trace_run.to_dict())
            if resp.status_code < 300:
                print(f"   📋 Trace posted → {trace_run.trace_id}")
            else:
                print(f"   ⚠ Trace POST returned {resp.status_code}")
    except Exception as exc:
        print(f"   ⚠ Trace POST failed (non-fatal): {exc}")


async def run_scenario(scenario: PatientScenario) -> None:
    patient_id = f"PAT-{int(time.time())}-{scenario.name}"
    visit_id = f"VISIT-{int(time.time())}-{scenario.name}"
    trace_id = make_trace_id()

    display_title = _scenario_display_title(scenario.name)
    print(f"🏥 Starting Scenario: {display_title}")
    print(f"   Description: {scenario.description}")
    print(f"   Patient ID: {patient_id}")
    print(f"   Visit ID: {visit_id}")
    print(f"   Trace ID: {trace_id}")
    print(f"   Profile: {scenario.patient_profile}")
    print("=" * 80)

    trace_run = TraceRun(
        trace_id=trace_id,
        scenario_name=scenario.name,
        visit_id=visit_id,
        patient_id=patient_id,
        patient_profile=scenario.patient_profile,
        started_at=datetime.now().astimezone().isoformat(),
    )

    # Phase 4: Inter-step clinical context threading (opt-in, harmless to existing agents)
    clinical_context: dict[str, Any] = {
        "patient_profile": dict(scenario.patient_profile or {}),
        # If medical_history is absent, keep an empty dict to remain backward compatible
        "medical_history": dict(getattr(scenario, "medical_history", {}) or {}),
        # Container for agent outputs by agent alias
        "agent_outputs": {},
        # Scenario metadata useful for downstream prompts/logic
        "_meta": {
            "scenario_name": scenario.name,
            "trace_id": trace_id,
        },
    }

    # Delegation engine – tracks handoff validation & context chaining
    try:
        from tools.delegation import (DelegationMonitor, HandoffResult,
                                      build_delegation_context,
                                      validate_handoff)
    except ImportError:
        from delegation import (DelegationMonitor, HandoffResult,
                                build_delegation_context, validate_handoff)

    try:
        from shared.nexus_common.clinical_handoff_rules import \
            apply_nhs_guardrails
    except Exception:
        from clinical_handoff_rules import apply_nhs_guardrails  # type: ignore

    profile = _scenario_simulation_profile(scenario)
    ai_agent_driven = _is_ai_agent_driven_enabled()
    ai_agent_intensity = _ai_agent_driven_intensity()
    if ai_agent_driven:
        profile = _agent_driven_profile(profile, ai_agent_intensity)
        print(
            "   🤖 AI agent-driven mode: enabled "
            f"(intensity={ai_agent_intensity}, variance={profile.get('variance_band')})"
        )
    rng = random.Random(int(profile.get("seed", _stable_seed(scenario.name))))

    clinical_context["_meta"]["ai_agent_driven"] = ai_agent_driven
    clinical_context["_meta"]["ai_agent_intensity"] = (
        ai_agent_intensity if ai_agent_driven else None
    )

    monitor = DelegationMonitor()
    completed_agents: set[str] = set()
    failed_agents: set[str] = set()
    guideline_refs_seen: set[str] = set()

    final_status = "final"
    prev_agent = "_start"
    for i, step in enumerate(scenario.journey_steps, 1):
        agent_alias = step["agent"]
        print(f"\nStep {i}/{len(scenario.journey_steps)}: {_agent_display_label(agent_alias)}")

        branch = _choose_simulation_branch(rng=rng, profile=profile)
        if branch != "nominal":
            print(f"   🎲 Simulation branch: {branch}")
        clinical_context["_meta"]["simulation_branch"] = branch

        # ── Handoff validation (Delegation paper §4.5) ──
        handoff_policy = step.get("handoff_policy")
        handoff_result: HandoffResult = validate_handoff(
            handoff_policy,
            clinical_context,
            completed_agents,
            failed_agents,
        )
        rationale = ""
        if isinstance(handoff_policy, dict):
            rationale = handoff_policy.get("clinical_rationale", "")
        monitor.record_handoff(
            prev_agent,
            agent_alias,
            i,
            handoff_result,
            rationale,
        )

        if handoff_result.state == "retry_pending":
            retry_after = handoff_result.retry_after_seconds or 0.0
            wait_seconds = max(0.0, min(30.0, retry_after))
            if wait_seconds > 0:
                print(f"   ⏳ Retry hold for {wait_seconds:.1f}s before escalation check")
                await asyncio.sleep(wait_seconds)
            handoff_result = validate_handoff(
                handoff_policy,
                clinical_context,
                completed_agents,
                failed_agents,
            )
            monitor.record_handoff(
                prev_agent,
                agent_alias,
                i,
                handoff_result,
                f"{rationale} (post-retry check)".strip(),
            )

        guardrail = apply_nhs_guardrails(
            step=step,
            handoff_policy=handoff_policy if isinstance(handoff_policy, dict) else None,
            clinical_context=clinical_context,
        )
        guideline_refs_seen.update(guardrail.guideline_refs)
        if handoff_result.allowed and not guardrail.allowed:
            escalation_target = None
            if isinstance(handoff_policy, dict):
                escalation_path = handoff_policy.get("escalation_path")
                if isinstance(escalation_path, list) and escalation_path:
                    escalation_target = str(escalation_path[0])
            if not escalation_target:
                escalation_target = "care_coordinator"
            handoff_result = HandoffResult(
                allowed=False,
                skipped=False,
                state="blocked_escalated",
                reason_code=guardrail.reason_code or "senior_review_required",
                reason=guardrail.reason or "Safety guardrail blocked this handoff",
                escalation_required=True,
                escalation_target=escalation_target,
                deadline_at=guardrail.senior_review_deadline,
                guideline_refs=guardrail.guideline_refs,
            )
            monitor.record_handoff(
                prev_agent,
                agent_alias,
                i,
                handoff_result,
                f"{rationale} (NHS guardrail)".strip(),
            )

        if not handoff_result.allowed:
            if handoff_result.skipped:
                print(f"   ⏭ {handoff_result.reason}")
            elif handoff_result.state == "rerouted":
                branch_name = ""
                if isinstance(handoff_policy, dict):
                    branch_name = str(handoff_policy.get("safe_fallback_branch") or "")
                print(f"   ↪ {handoff_result.reason}")
                if branch_name:
                    clinical_context.setdefault("safe_fallback_branches", []).append(
                        {
                            "step": i,
                            "agent": agent_alias,
                            "branch": branch_name,
                            "reason": handoff_result.reason,
                        }
                    )
                    trace_run.safe_fallback_taken = True
            else:
                print(f"   🚫 {handoff_result.reason}")
                final_status = "error"
            prev_agent = agent_alias
            if "delay" in step:
                await asyncio.sleep(step["delay"])
            continue

        # ── Build delegation context (§4.3 structural transparency) ──
        delegation_info = build_delegation_context(
            step,
            clinical_context,
            handoff_policy,
        )

        step_params = _resolve_context_template(step["params"], clinical_context)
        step_params["patient_id"] = patient_id
        step_params["visit_id"] = visit_id
        # Inject accumulated clinical context so agents can generate realistic outputs
        # Existing agents that ignore this field remain unaffected
        step_params["clinical_context"] = clinical_context
        step_params["delegation"] = delegation_info
        step_params["simulation"] = {
            "seed": profile.get("seed"),
            "variance_band": profile.get("variance_band"),
            "allowed_branches": profile.get("allowed_branches"),
            "selected_branch": branch,
        }
        if ai_agent_driven:
            step_params["agent_autonomy"] = {
                "enabled": True,
                "intensity": ai_agent_intensity,
                "objective": "Stress-test NEXUS-A2A robustness with bounded autonomous decisions",
                "policy": {
                    "preserve_safety_guardrails": True,
                    "allow_dynamic_handoff_strategy": True,
                    "prefer_contextual_reasoning": True,
                },
                "stress": {
                    "inject_non_nominal_probability": True,
                    "encourage_parallel_handoff_checks": ai_agent_intensity in {"medium", "high"},
                },
            }
        task_id = f"{visit_id}-{step['agent']}-{i}"
        rpc_url = resolve_agent_rpc_url(step["agent"])

        try:
            result, step_event = await make_jsonrpc_call(
                rpc_url,
                step["method"],
                step_params,
                task_id,
                trace_id=trace_id,
                step_index=i,
                scenario_name=scenario.name,
                patient_id=patient_id,
                visit_id=visit_id,
            )
        except (Exception, asyncio.CancelledError) as exc:
            # Safety net: catch any unhandled exception (including
            # asyncio.CancelledError which is BaseException in 3.9+)
            # so one step failure never crashes the entire scenario run.
            print(f"   ❌ Unhandled error in step {i}: {exc or type(exc).__name__}")
            result = {"error": str(exc)}
            step_event = None
            failed_agents.add(agent_alias)
            final_status = "error"
            prev_agent = agent_alias
            if "delay" in step:
                await asyncio.sleep(step["delay"])
            continue

        if step_event is not None:
            trace_run.add_step(step_event)
            if step_event.status == "error":
                final_status = "error"
                failed_agents.add(agent_alias)
            else:
                completed_agents.add(agent_alias)
        else:
            completed_agents.add(agent_alias)

        # Merge agent output back into the clinical context for downstream steps
        try:
            # JSON-RPC envelope typically has {"jsonrpc":"2.0","id":...,"result":{...}}
            env = result if isinstance(result, dict) else {}
            payload = env.get("result", env)
            # Store under agent alias; also keep the last_step for quick reference
            clinical_context["agent_outputs"][step["agent"]] = payload
            clinical_context["last_step"] = {
                "agent": step["agent"],
                "method": step["method"],
                "result": payload,
                "index": i,
            }
            params = step.get("params") if isinstance(step.get("params"), dict) else {}
            transition = (
                params.get("care_transition")
                if isinstance(params.get("care_transition"), dict)
                else {}
            )
            handover = (
                transition.get("handover") if isinstance(transition.get("handover"), dict) else {}
            )
            if handover:
                clinical_context["handover"] = handover
        except Exception:
            # Non-fatal; context threading is best-effort
            pass

        prev_agent = agent_alias
        if "delay" in step:
            await asyncio.sleep(step["delay"])

    # Attach delegation chain to trace for dashboard rendering
    trace_run.delegation_chain = monitor.to_chain()
    all_refs = set(guideline_refs_seen)
    for item in trace_run.delegation_chain:
        for ref in item.get("guideline_refs", []):
            if ref:
                all_refs.add(str(ref))
    trace_run.guideline_refs = sorted(all_refs)
    blocked_events = [
        e for e in trace_run.delegation_chain if e.get("state") == "blocked_escalated"
    ]
    degraded_events = [
        e
        for e in trace_run.delegation_chain
        if e.get("state") in {"degraded_allowed", "rerouted", "retry_pending"}
    ]
    if blocked_events:
        trace_run.handover_contract_status = "blocked"
    elif degraded_events:
        trace_run.handover_contract_status = "degraded"
    else:
        trace_run.handover_contract_status = "complete"
    trigger_event = next(
        (e for e in trace_run.delegation_chain if e.get("escalation_required")), None
    )
    if trigger_event:
        trace_run.escalation_trigger = str(
            trigger_event.get("reason_code") or "escalation_required"
        )
        trace_run.senior_review_deadline = trigger_event.get("deadline_at")
    trace_run.safe_fallback_taken = bool(
        trace_run.safe_fallback_taken
        or any(bool(e.get("safe_fallback_taken")) for e in trace_run.delegation_chain)
    )
    trace_run.finalize(status=final_status)
    await _post_trace_run(trace_run)

    skipped = monitor.skipped_count
    blocked = monitor.failed_count
    retries = sum(1 for e in trace_run.delegation_chain if e.get("state") == "retry_pending")
    rerouted = sum(1 for e in trace_run.delegation_chain if e.get("state") == "rerouted")
    print(f"\n✅ Scenario '{display_title}' completed!")
    print(f"   Duration: ~{scenario.expected_duration} seconds")
    if skipped or blocked or retries or rerouted:
        print(
            "   Delegation: "
            f"{skipped} skipped, {blocked} blocked, {retries} retry-pending, {rerouted} rerouted"
        )
    print("=" * 80)


async def run_multiple_scenarios(
    scenario_names: list[str] | None = None,
    parallel: bool = False,
    *,
    include_clinical_negative: bool = False,
    include_representative_expansion: bool = False,
) -> None:
    if scenario_names is None:
        scenarios_to_run = SCENARIOS + _load_additional_scenarios()
        if include_clinical_negative:
            scenarios_to_run = scenarios_to_run + _load_clinical_negative_scenarios()
        if include_representative_expansion:
            scenarios_to_run = scenarios_to_run + _load_representative_scenarios()
    else:
        combined = SCENARIOS + _load_additional_scenarios()
        if include_clinical_negative:
            combined = combined + _load_clinical_negative_scenarios()
        if include_representative_expansion:
            combined = combined + _load_representative_scenarios()
        wanted = set(scenario_names)
        scenarios_to_run = [s for s in combined if s.name in wanted]

    if not scenarios_to_run:
        print("❌ No matching scenarios found")
        return

    print(f"🚀 Running {len(scenarios_to_run)} scenario(s)")
    print(f"   Mode: {'Parallel' if parallel else 'Sequential'}")
    print(f"   Retry profile: {ACTIVE_RETRY_MODE}")

    if parallel:
        await asyncio.gather(*(run_scenario(s) for s in scenarios_to_run))
        return

    for scenario in scenarios_to_run:
        await run_scenario(scenario)
        await asyncio.sleep(2)


async def list_scenarios() -> None:
    print("📋 Canonical HelixCare Patient Visit Scenarios (10):")
    print("=" * 80)
    for i, scenario in enumerate(SCENARIOS, 1):
        print(f"{i:2d}. {_scenario_display_title(scenario.name)}")
        print(f"    {scenario.description}")
        print(
            "    Patient: "
            f"{scenario.patient_profile['age']}yo "
            f"{scenario.patient_profile['gender']}, "
            f"{scenario.patient_profile['chief_complaint']}"
        )
        print(f"    Steps: {len(scenario.journey_steps)}, Duration: ~{scenario.expected_duration}s")
        print()


def save_scenarios_to_file() -> None:
    scenarios_data: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        scenarios_data.append(
            {
                "name": scenario.name,
                "description": scenario.description,
                "patient_profile": scenario.patient_profile,
                "journey_steps": scenario.journey_steps,
                "expected_duration": scenario.expected_duration,
                # Include optional enriched history when present
                "medical_history": getattr(scenario, "medical_history", {}),
                "simulation_profile": getattr(scenario, "simulation_profile", {}),
                "negative_class": getattr(scenario, "negative_class", None),
                "expected_escalation": getattr(scenario, "expected_escalation", None),
                "expected_safe_outcome": getattr(scenario, "expected_safe_outcome", None),
            }
        )

    with open("tools/helixcare_scenarios.json", "w", encoding="utf-8") as f:
        json.dump(scenarios_data, f, indent=2, default=str)

    print("💾 Scenarios saved to tools/helixcare_scenarios.json")


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="HelixCare Patient Visit Scenarios",
    )
    parser.add_argument("--list", action="store_true", help="List all scenarios")
    parser.add_argument("--run", nargs="*", help="Run specific scenario(s)")
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    parser.add_argument("--parallel", action="store_true", help="Run in parallel")
    parser.add_argument("--save", action="store_true", help="Save scenarios to JSON")
    parser.add_argument(
        "--retry-mode",
        choices=sorted(RETRY_MODE_CONFIGS.keys()),
        help="Retry profile: strict-zero (validation), balanced (default), fast (load)",
    )
    parser.add_argument(
        "--gateway",
        nargs="?",
        const="http://localhost:8100",
        help=(
            "Route agent RPC via on-demand gateway. Optional URL (default: http://localhost:8100)."
        ),
    )
    parser.add_argument(
        "--simulation-seed",
        type=int,
        help="Deterministic seed for bounded stochastic branch selection.",
    )
    parser.add_argument(
        "--variance-band",
        choices=["low", "medium", "high"],
        help="Stochastic variance band (default from scenario profile).",
    )
    parser.add_argument(
        "--include-clinical-negatives",
        action="store_true",
        help="Include explicit clinical-handoff negative journeys.",
    )
    parser.add_argument(
        "--include-representative-expansion",
        action="store_true",
        help="Include expanded representative scenario corpus.",
    )
    parser.add_argument(
        "--ai-agent-driven",
        action="store_true",
        help="Enable bounded AI-agent-driven workflow mode for robustness stress testing.",
    )
    parser.add_argument(
        "--agent-driven-intensity",
        choices=["low", "medium", "high"],
        default="high",
        help="Agent-driven autonomy intensity when --ai-agent-driven is enabled.",
    )

    args = parser.parse_args()

    if args.retry_mode:
        configure_retry_mode(args.retry_mode)
    if args.gateway is not None:
        configure_gateway_url(args.gateway)
    if args.simulation_seed is not None:
        os.environ["HELIXCARE_SIMULATION_SEED"] = str(args.simulation_seed)
    if args.variance_band:
        os.environ["HELIXCARE_VARIANCE_BAND"] = args.variance_band
    if args.ai_agent_driven:
        os.environ["HELIXCARE_AI_AGENT_DRIVEN"] = "true"
        os.environ["HELIXCARE_AI_AGENT_DRIVEN_INTENSITY"] = args.agent_driven_intensity

    print(f"⚙ Active retry profile: {ACTIVE_RETRY_MODE}")
    if ON_DEMAND_GATEWAY_URL:
        print(f"⚙ On-demand gateway routing: {ON_DEMAND_GATEWAY_URL}")
    else:
        print("⚙ On-demand gateway routing: disabled (direct agent ports)")
    if os.getenv("HELIXCARE_SIMULATION_SEED"):
        print(f"⚙ Simulation seed: {os.getenv('HELIXCARE_SIMULATION_SEED')}")
    if os.getenv("HELIXCARE_VARIANCE_BAND"):
        print(f"⚙ Variance band: {os.getenv('HELIXCARE_VARIANCE_BAND')}")
    if _is_ai_agent_driven_enabled():
        print(f"⚙ AI agent-driven mode: enabled ({_ai_agent_driven_intensity()})")
    if args.include_representative_expansion:
        print("⚙ Representative expansion: enabled")

    if args.save:
        save_scenarios_to_file()
        return
    if args.list:
        await list_scenarios()
        return

    scenarios_to_run: list[str] = []
    if args.run:
        scenarios_to_run = args.run
    elif args.all:
        combined = SCENARIOS + _load_additional_scenarios()
        if args.include_clinical_negatives:
            combined.extend(_load_clinical_negative_scenarios())
        if args.include_representative_expansion:
            combined.extend(_load_representative_scenarios())
        scenarios_to_run = [s.name for s in combined]

    if scenarios_to_run:
        await run_multiple_scenarios(
            scenarios_to_run,
            args.parallel,
            include_clinical_negative=args.include_clinical_negatives,
            include_representative_expansion=args.include_representative_expansion,
        )
        return

    print("Use --list to see available scenarios")
    print("Use --run <name> to run specific scenarios")
    print("Use --all to run all scenarios")
    print("Use --save to save scenarios to file")


if __name__ == "__main__":
    asyncio.run(main())
