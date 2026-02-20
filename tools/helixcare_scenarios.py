#!/usr/bin/env python3
"""HelixCare canonical patient-visit scenarios (definitive set of 10)."""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import time
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

BASE_URLS = {
    "triage": "http://localhost:8021",
    "diagnosis": "http://localhost:8022",
    "openhie_mediator": "http://localhost:8023",
    "imaging": "http://localhost:8024",
    "pharmacy": "http://localhost:8025",
    "bed_manager": "http://localhost:8026",
    "discharge": "http://localhost:8027",
    "followup": "http://localhost:8028",
    "coordinator": "http://localhost:8029",
    "transcriber": "http://localhost:8031",
    "summariser": "http://localhost:8032",
    "ehr_writer": "http://localhost:8033",
    "primary_care": "http://localhost:8034",
    "specialty_care": "http://localhost:8035",
    "telehealth": "http://localhost:8036",
    "home_visit": "http://localhost:8037",
    "ccm": "http://localhost:8038",
    "clinician_avatar": "http://localhost:8039",
    "insurer_agent": "http://localhost:8041",
    "provider_agent": "http://localhost:8042",
    "consent_analyser": "http://localhost:8043",
    "hitl_ui": "http://localhost:8044",
    "hospital_reporter": "http://localhost:8051",
    "osint_agent": "http://localhost:8052",
    "central_surveillance": "http://localhost:8053",
}
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

    return isinstance(
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
    )


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
    async with httpx.AsyncClient(timeout=timeout) as client:
        last_error = "unknown error"
        attempts_made = 0
        start_time = time.perf_counter()
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
            except Exception as exc:
                last_error = str(exc)
                retriable = _is_retriable_error(exc)
                print(
                    "   ❌ Attempt "
                    f"{attempt}/{ACTIVE_RETRY_CONFIG.max_rpc_attempts} failed"
                    f" ({'retriable' if retriable else 'non-retriable'}): {exc}"
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
) -> dict[str, Any]:
    return {
        "agent": agent,
        "method": method,
        "params": params,
        "delay": delay,
    }


def _future(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).isoformat()


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
            _step(
                "diagnosis",
                "tasks/sendSubscribe",
                {
                    "symptoms": "fatigue, headaches",
                    "differential_diagnosis": ["Hypertension", "Anemia", "Thyroid dysfunction"],
                },
                2,
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
            ),
        ],
        expected_duration=12,
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
            _step(
                "diagnosis",
                "tasks/sendSubscribe",
                {
                    "symptoms": "exertional chest discomfort",
                    "differential_diagnosis": ["Stable angina", "GERD", "Aortic stenosis"],
                },
                2,
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
            ),
        ],
        expected_duration=14,
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
            _step(
                "diagnosis",
                "tasks/sendSubscribe",
                {
                    "symptoms": "recurrent migraines, photophobia",
                    "differential_diagnosis": ["Migraine", "Medication overuse headache"],
                },
                2,
            ),
            _step(
                "pharmacy",
                "pharmacy/recommend",
                {"task": {"med_plan": ["Ibuprofen"], "allergies": [], "current_medications": []}},
                1,
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
            ),
        ],
        expected_duration=10,
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
            _step(
                "primary_care",
                "primary_care/manage_visit",
                {"visit_mode": "audio_only", "complaint": "dizziness after medication change"},
            ),
            _step(
                "pharmacy", "pharmacy/check_interactions", {"drugs": ["Lisinopril", "Ibuprofen"]}, 1
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
            ),
        ],
        expected_duration=9,
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
            _step(
                "primary_care",
                "primary_care/manage_visit",
                {"visit_mode": "home", "complaint": "falls and mobility decline"},
                2,
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
            ),
        ],
        expected_duration=15,
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
            _step(
                "primary_care",
                "primary_care/manage_visit",
                {"visit_mode": "care_management", "complaint": "goal and plan review"},
                1,
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
            ),
            _step(
                "pharmacy",
                "pharmacy/check_interactions",
                {"drugs": ["Metformin", "Lisinopril", "Aspirin"]},
                1,
            ),
        ],
        expected_duration=11,
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
            _step(
                "diagnosis",
                "tasks/sendSubscribe",
                {
                    "symptoms": "wheezing and dyspnea",
                    "differential_diagnosis": ["Asthma exacerbation", "Pneumonia", "Pneumothorax"],
                },
                2,
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
            ),
            _step(
                "pharmacy",
                "tasks/sendSubscribe",
                {"task": {"med_plan": ["Albuterol", "Prednisone"], "allergies": []}},
                1,
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
            ),
        ],
        expected_duration=16,
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
            ),
        ],
        expected_duration=14,
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
            _step(
                "pharmacy",
                "tasks/sendSubscribe",
                {"task": {"med_plan": ["Amoxicillin", "Oxygen"], "allergies": []}},
                1,
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
            ),
            _step("ccm", "ccm/monthly_review", {"conditions": ["COPD"], "monthly_minutes": 20}, 1),
        ],
        expected_duration=12,
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
            ),
            _step("ccm", "ccm/monthly_review", {"conditions": ["CHF"], "monthly_minutes": 22}, 1),
        ],
        expected_duration=11,
    ),
]


def _load_additional_scenarios() -> list[PatientScenario]:
    """Lazily load additive variants to avoid eager circular imports."""
    try:
        from additional_scenarios import ADDITIONAL_SCENARIOS

        return list(ADDITIONAL_SCENARIOS)
    except Exception:
        try:
            from tools.additional_scenarios import ADDITIONAL_SCENARIOS

            return list(ADDITIONAL_SCENARIOS)
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

    print(f"🏥 Starting Scenario: {scenario.name}")
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

    final_status = "final"
    for i, step in enumerate(scenario.journey_steps, 1):
        print(f"\nStep {i}/{len(scenario.journey_steps)}: {step['agent'].upper()}")
        step_params = _resolve_context_template(step["params"], clinical_context)
        step_params["patient_id"] = patient_id
        step_params["visit_id"] = visit_id
        # Inject accumulated clinical context so agents can generate realistic outputs
        # Existing agents that ignore this field remain unaffected
        step_params["clinical_context"] = clinical_context
        task_id = f"{visit_id}-{step['agent']}-{i}"
        rpc_url = resolve_agent_rpc_url(step["agent"])

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

        if step_event is not None:
            trace_run.add_step(step_event)
            if step_event.status == "error":
                final_status = "error"

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
        except Exception:
            # Non-fatal; context threading is best-effort
            pass

        if "delay" in step:
            await asyncio.sleep(step["delay"])

    trace_run.finalize(status=final_status)
    await _post_trace_run(trace_run)

    print(f"\n✅ Scenario '{scenario.name}' completed!")
    print(f"   Duration: ~{scenario.expected_duration} seconds")
    print("=" * 80)


async def run_multiple_scenarios(
    scenario_names: list[str] | None = None,
    parallel: bool = False,
) -> None:
    if scenario_names is None:
        scenarios_to_run = SCENARIOS
    else:
        combined = SCENARIOS + _load_additional_scenarios()
        scenarios_to_run = [s for s in combined if s.name in scenario_names]

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
        print(f"{i:2d}. {scenario.name}")
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

    args = parser.parse_args()

    if args.retry_mode:
        configure_retry_mode(args.retry_mode)
    if args.gateway is not None:
        configure_gateway_url(args.gateway)

    print(f"⚙ Active retry profile: {ACTIVE_RETRY_MODE}")
    if ON_DEMAND_GATEWAY_URL:
        print(f"⚙ On-demand gateway routing: {ON_DEMAND_GATEWAY_URL}")
    else:
        print("⚙ On-demand gateway routing: disabled (direct agent ports)")

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
        scenarios_to_run = [s.name for s in SCENARIOS]

    if scenarios_to_run:
        await run_multiple_scenarios(scenarios_to_run, args.parallel)
        return

    print("Use --list to see available scenarios")
    print("Use --run <name> to run specific scenarios")
    print("Use --all to run all scenarios")
    print("Use --save to save scenarios to file")


if __name__ == "__main__":
    asyncio.run(main())
