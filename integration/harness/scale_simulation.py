"""Large-scale agent simulation for the integration harness.

Simulates national-scale healthcare workloads flowing through the full chain:
    GHARRA discovery → Nexus routing → Real test agents

Reuses existing infrastructure:
  - PatientScenario model from Nexus tools/helixcare_scenarios.py
  - Load matrix profiles from Nexus tools/generate_load_matrix.py
  - Rate limiter tiers from GHARRA core/pricing.py
  - Locust patterns from GHARRA tests/load/locustfile.py

Scale profiles (configurable):
  - smoke:     10 patients, 2 hospitals, 1 insurer
  - small:     100 patients, 10 hospitals, 5 insurers
  - medium:    1,000 patients, 50 hospitals, 10 insurers
  - large:     10,000 patients, 500 hospitals, 100 insurers
  - national:  100,000 patients, 2,000 hospitals, 500 insurers

Usage:
    from harness.scale_simulation import ScaleSimulator, ScaleProfile
    sim = ScaleSimulator(gharra_url, nexus_url)
    report = await sim.run(ScaleProfile.MEDIUM)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import platform
import random
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import httpx
import jwt

logger = logging.getLogger("harness.scale_simulation")

GHARRA_BASE_URL = os.getenv("GHARRA_BASE_URL", "http://localhost:8400")
NEXUS_GATEWAY_URL = os.getenv("NEXUS_GATEWAY_URL", "http://localhost:8100")
NEXUS_JWT_SECRET = os.getenv("NEXUS_JWT_SECRET", "integration-test-secret")


# ── Scale profiles ─────────────────────────────────────────────────────

class ScaleProfile(str, Enum):
    SMOKE = "smoke"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    NATIONAL = "national"


SCALE_CONFIGS = {
    ScaleProfile.SMOKE:    {"patients": 10,      "hospitals": 2,    "insurers": 1,   "telemed": 1,   "concurrency": 5},
    ScaleProfile.SMALL:    {"patients": 100,     "hospitals": 10,   "insurers": 5,   "telemed": 3,   "concurrency": 20},
    ScaleProfile.MEDIUM:   {"patients": 1_000,   "hospitals": 50,   "insurers": 10,  "telemed": 10,  "concurrency": 50},
    ScaleProfile.LARGE:    {"patients": 10_000,  "hospitals": 500,  "insurers": 100, "telemed": 50,  "concurrency": 100},
    ScaleProfile.NATIONAL: {"patients": 100_000, "hospitals": 2000, "insurers": 500, "telemed": 200, "concurrency": 250},
}


# ── Clinical data generators (reuse Nexus patterns) ───────────────────

CHIEF_COMPLAINTS = [
    "chest pain", "shortness of breath", "abdominal pain", "headache",
    "fever", "nausea and vomiting", "back pain", "syncope",
    "palpitations", "stroke symptoms", "allergic reaction",
    "asthma exacerbation", "hypertensive emergency", "seizure",
    "altered mental status",
]

URGENCY_LEVELS = ["critical", "high", "medium", "low", "routine"]

# Real Nexus agents available through the on-demand gateway, grouped by
# the workload type they serve.  Each agent is registered in GHARRA at
# startup so every invocation flows through the real registry.
NEXUS_AGENT_ROLES = {
    "hospital": [
        {"alias": "triage",      "capability": "clinical-triage",       "jurisdiction": "IE"},
        {"alias": "diagnosis",   "capability": "clinical-diagnosis",    "jurisdiction": "GB"},
        {"alias": "imaging",     "capability": "radiology-imaging",     "jurisdiction": "US"},
        {"alias": "pharmacy",    "capability": "pharmacy-dispensing",    "jurisdiction": "DE"},
        {"alias": "bed_manager", "capability": "bed-management",        "jurisdiction": "IE"},
        {"alias": "discharge",   "capability": "discharge-planning",    "jurisdiction": "GB"},
        {"alias": "coordinator", "capability": "care-coordination",     "jurisdiction": "IE"},
    ],
    "insurer": [
        {"alias": "insurer",          "capability": "insurance-auth",   "jurisdiction": "US"},
        {"alias": "consent_analyser", "capability": "consent-analysis", "jurisdiction": "GB"},
    ],
    "telemed": [
        {"alias": "telehealth",  "capability": "telemedicine-session",  "jurisdiction": "IE"},
        {"alias": "transcriber", "capability": "transcription",         "jurisdiction": "GB"},
        {"alias": "summariser",  "capability": "clinical-summary",      "jurisdiction": "GB"},
    ],
    "primary_care": [
        {"alias": "primary_care",   "capability": "primary-care",       "jurisdiction": "IE"},
        {"alias": "specialty_care", "capability": "specialty-referral",  "jurisdiction": "GB"},
        {"alias": "followup",       "capability": "followup-scheduling","jurisdiction": "IE"},
    ],
}

# Flat list for backward compatibility — built from canonical seed agents
REGISTERED_AGENTS = [
    {"agent_id": "gharra://ie/agents/triage-e2e", "alias": "triage"},
    {"agent_id": "gharra://gb/agents/referral-e2e", "alias": "diagnosis"},
    {"agent_id": "gharra://us/agents/radiology-e2e", "alias": "imaging"},
    {"agent_id": "gharra://de/agents/pathology-e2e", "alias": "pharmacy"},
]


def _generate_patient(patient_num: int, hospital_id: int) -> dict[str, Any]:
    """Generate a patient profile matching Nexus PatientScenario format."""
    age = random.randint(1, 95)
    return {
        "patient_id": f"P-{patient_num:08d}",
        "encounter_id": f"E-{uuid.uuid4().hex[:12].upper()}",
        "hospital_id": f"H-{hospital_id:05d}",
        "age": age,
        "gender": random.choice(["male", "female"]),
        "chief_complaint": random.choice(CHIEF_COMPLAINTS),
        "urgency": random.choice(URGENCY_LEVELS),
        "medical_history": {
            "past_medical_history": [],
            "medications": [],
            "allergies": [],
        },
    }


# ── Metrics tracking ──────────────────────────────────────────────────

@dataclass
class StepMetrics:
    """Metrics for a single simulation step."""
    step: str
    success: int = 0
    failure: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0
    latencies: list[float] = field(default_factory=list)

    def record(self, elapsed_ms: float, ok: bool) -> None:
        if ok:
            self.success += 1
        else:
            self.failure += 1
        self.total_ms += elapsed_ms
        self.min_ms = min(self.min_ms, elapsed_ms)
        self.max_ms = max(self.max_ms, elapsed_ms)
        self.latencies.append(elapsed_ms)

    @property
    def count(self) -> int:
        return self.success + self.failure

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count else 0

    @property
    def p95_ms(self) -> float:
        if not self.latencies:
            return 0
        s = sorted(self.latencies)
        idx = int(len(s) * 0.95)
        return s[min(idx, len(s) - 1)]

    @property
    def p99_ms(self) -> float:
        if not self.latencies:
            return 0
        s = sorted(self.latencies)
        idx = int(len(s) * 0.99)
        return s[min(idx, len(s) - 1)]

    @property
    def error_rate(self) -> float:
        return self.failure / self.count if self.count else 0


def _get_infrastructure() -> dict[str, Any]:
    """Collect host infrastructure metadata for report context."""
    info: dict[str, Any] = {
        "cpu_count": os.cpu_count(),
        "platform": sys.platform,
        "python_version": platform.python_version(),
        "architecture": platform.machine(),
    }
    try:
        import psutil  # type: ignore[import-untyped]
        info["memory_gb"] = round(psutil.virtual_memory().total / 1e9, 1)
    except ImportError:
        info["memory_gb"] = None
    return info


@dataclass
class SimulationReport:
    """Complete simulation run report with deployment context metadata."""
    profile: str
    config: dict[str, int]
    total_tasks: int = 0
    total_success: int = 0
    total_failure: int = 0
    total_elapsed_s: float = 0.0
    throughput_rps: float = 0.0
    steps: dict[str, StepMetrics] = field(default_factory=dict)

    # ── Sprint 1 additions: deployment context and metadata ──
    deployment_context: str = field(
        default_factory=lambda: os.getenv("SCALE_DEPLOYMENT_CONTEXT", "docker_local"),
    )
    infrastructure: dict[str, Any] = field(default_factory=_get_infrastructure)
    started_at: str = ""
    completed_at: str = ""
    warmup_elapsed_s: float = 0.0
    warmup_agents_responsive: int = 0
    warmup_agents_total: int = 0
    caveats: list[str] = field(default_factory=list)
    report_hash: str = ""

    def _default_caveats(self) -> list[str]:
        """Generate caveats based on deployment context."""
        ctx = self.deployment_context
        caveats = []
        if ctx == "docker_local":
            caveats.append(
                "Docker-local deployment. Shared CPU/memory. "
                "No network latency. Results not representative of production."
            )
        elif ctx == "cloud_single_region":
            caveats.append(
                "Managed Kubernetes single region. Production-grade networking. "
                "Cross-region latency not included."
            )
        elif ctx == "cloud_multi_region":
            caveats.append(
                "Multi-region deployment. Cross-region latency included in measurements."
            )
        caveats.append("Synthetic patient workload (random chief complaints and urgency levels).")
        return caveats

    def summary(self) -> dict[str, Any]:
        result = {
            "profile": self.profile,
            "config": self.config,
            "total_tasks": self.total_tasks,
            "success": self.total_success,
            "failure": self.total_failure,
            "error_rate": f"{self.total_failure / self.total_tasks:.2%}" if self.total_tasks else "0%",
            "elapsed_s": round(self.total_elapsed_s, 2),
            "throughput_rps": round(self.throughput_rps, 1),
            "steps": {
                name: {
                    "count": m.count,
                    "success": m.success,
                    "failure": m.failure,
                    "avg_ms": round(m.avg_ms, 1),
                    "p95_ms": round(m.p95_ms, 1),
                    "p99_ms": round(m.p99_ms, 1),
                    "min_ms": round(m.min_ms, 1) if m.min_ms != float("inf") else 0,
                    "max_ms": round(m.max_ms, 1),
                    "error_rate": f"{m.error_rate:.2%}",
                }
                for name, m in self.steps.items()
            },
            # ── Metadata ──
            "deployment_context": self.deployment_context,
            "infrastructure": self.infrastructure,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "warmup_elapsed_s": round(self.warmup_elapsed_s, 2),
            "warmup_agents_responsive": self.warmup_agents_responsive,
            "warmup_agents_total": self.warmup_agents_total,
            "caveats": self.caveats or self._default_caveats(),
            "report_hash": self.report_hash,
        }
        return result

    def compute_hash(self) -> str:
        """Compute SHA-256 of the canonical JSON report (excluding report_hash itself)."""
        s = self.summary()
        s.pop("report_hash", None)
        canonical = json.dumps(s, sort_keys=True, separators=(",", ":"))
        self.report_hash = hashlib.sha256(canonical.encode()).hexdigest()
        return self.report_hash

    def save(self, path: str | Path) -> Path:
        """Save the report as JSON to the given path."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self.compute_hash()
        p.write_text(json.dumps(self.summary(), indent=2))
        logger.info("Simulation report saved to %s", p)
        return p


# ── Core simulator ────────────────────────────────────────────────────

class ScaleSimulator:
    """Runs large-scale patient workflow simulations through GHARRA → Nexus.

    Every task flows through the real production path:
    1. Register agents in GHARRA (real registry entries, not stubs)
    2. Resolve agent via GHARRA (GET /v1/agents/{id})
    3. Route task via Nexus gateway (POST /rpc/{agent})
    4. Nexus starts real agent processes and delivers JSON-RPC
    5. Collect response

    No mocks, no stubs, no simulated agents.  All traffic flows through
    the real GHARRA registry and real Nexus on-demand gateway.

    Tasks run concurrently via asyncio.Semaphore to control load.
    """

    def __init__(
        self,
        gharra_url: str | None = None,
        nexus_url: str | None = None,
        jwt_secret: str | None = None,
    ):
        self._gharra_url = (gharra_url or GHARRA_BASE_URL).rstrip("/")
        self._nexus_url = (nexus_url or NEXUS_GATEWAY_URL).rstrip("/")
        self._jwt_secret = jwt_secret or NEXUS_JWT_SECRET
        self._report: SimulationReport | None = None
        self._scale_agents: list[dict[str, str]] = []  # registered at run start
        self._responsive_agents: list[dict[str, str]] = []  # warmup-validated
        self._cached_jwt: str | None = None
        self._jwt_expiry: float = 0

    def _mint_jwt(self) -> str:
        """Mint (or return cached) JWT for Nexus authentication.

        Tokens are cached for 50 minutes to avoid per-invocation overhead
        at large scale while staying well within the 1-hour TTL.
        """
        now = time.time()
        if self._cached_jwt and now < self._jwt_expiry:
            return self._cached_jwt
        iat = int(now)
        self._cached_jwt = jwt.encode(
            {"sub": "scale-sim", "iat": iat, "exp": iat + 3600, "scope": "nexus:invoke"},
            self._jwt_secret,
            algorithm="HS256",
        )
        self._jwt_expiry = now + 3000  # refresh after 50 mins
        return self._cached_jwt

    async def _register_scale_agents(self) -> list[dict[str, str]]:
        """Register real Nexus agents in GHARRA for scale testing.

        Each agent in NEXUS_AGENT_ROLES maps to a real Nexus on-demand gateway
        agent.  This method creates GHARRA registry entries pointing to the
        real Nexus endpoints so all resolution flows through the real registry.
        """
        agents: list[dict[str, str]] = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for role, role_agents in NEXUS_AGENT_ROLES.items():
                for agent_def in role_agents:
                    alias = agent_def["alias"]
                    agent_id = f"gharra://{agent_def['jurisdiction'].lower()}/agents/scale-{alias}"
                    body = {
                        "agent_id": agent_id,
                        "display_name": f"Scale {alias}",
                        "jurisdiction": agent_def["jurisdiction"],
                        "endpoints": [{
                            "url": f"http://nexus-gateway:8100/rpc/{alias}",
                            "protocol": "nexus-a2a-jsonrpc",
                            "priority": 10,
                            "weight": 100,
                        }],
                        "capabilities": {
                            "protocols": ["nexus-a2a-jsonrpc"],
                            "domain": [agent_def["capability"]],
                        },
                    }
                    resp = await client.post(
                        f"{self._gharra_url}/v1/agents",
                        json=body,
                        headers={"X-Idempotency-Key": str(uuid.uuid4())},
                    )
                    if resp.status_code in (201, 409):
                        agents.append({"agent_id": agent_id, "alias": alias, "role": role})
                        logger.debug("Registered scale agent: %s → %s", alias, agent_id)
                    else:
                        logger.warning("Failed to register %s: %d", alias, resp.status_code)

        # Also include the canonical seed agents
        for a in REGISTERED_AGENTS:
            agents.append({**a, "role": "hospital"})

        logger.info("Registered %d scale agents in GHARRA", len(agents))
        return agents

    async def _resolve_agent(
        self,
        client: httpx.AsyncClient,
        agent_id: str,
        metrics: StepMetrics,
        max_retries: int = 2,
    ) -> dict[str, Any] | None:
        """Step 1: Resolve agent via GHARRA."""
        for attempt in range(1 + max_retries):
            t0 = time.monotonic()
            try:
                resp = await client.get(f"{self._gharra_url}/v1/agents/{agent_id}")
                elapsed = (time.monotonic() - t0) * 1000
                if resp.status_code >= 500 and attempt < max_retries:
                    await asyncio.sleep(0.3 * (attempt + 1))
                    continue
                ok = resp.status_code < 400
                metrics.record(elapsed, ok)
                return resp.json() if ok else None
            except Exception:
                elapsed = (time.monotonic() - t0) * 1000
                if attempt < max_retries:
                    await asyncio.sleep(0.3 * (attempt + 1))
                    continue
                metrics.record(elapsed, False)
                return None
        metrics.record(0, False)
        return None

    async def _invoke_agent(
        self,
        client: httpx.AsyncClient,
        agent_alias: str,
        patient: dict[str, Any],
        metrics: StepMetrics,
        max_retries: int = 2,
    ) -> bool:
        """Step 2: Invoke agent via Nexus gateway.

        Retries on 503 (agent cold-start) with backoff, matching the
        retry pattern in Nexus tools/helixcare_scenarios.py.
        """
        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "patient_id": patient["patient_id"],
                "encounter_id": patient["encounter_id"],
                "clinical_data": {
                    "chief_complaint": patient["chief_complaint"],
                    "urgency": patient["urgency"],
                    "age": patient["age"],
                },
            },
            "id": str(uuid.uuid4()),
        }
        token = self._mint_jwt()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        for attempt in range(1 + max_retries):
            t0 = time.monotonic()
            try:
                resp = await client.post(
                    f"{self._nexus_url}/rpc/{agent_alias}",
                    json=payload,
                    headers=headers,
                )
                elapsed = (time.monotonic() - t0) * 1000
                if resp.status_code == 503 and attempt < max_retries:
                    # Agent still starting — back off and retry
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                ok = resp.status_code < 500
                metrics.record(elapsed, ok)
                return ok
            except Exception:
                elapsed = (time.monotonic() - t0) * 1000
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                metrics.record(elapsed, False)
                return False
        metrics.record(0, False)
        return False

    async def _warmup(
        self,
        client: httpx.AsyncClient,
        n_warmup: int = 3,
    ) -> tuple[list[dict[str, str]], float]:
        """Run warmup cycles to discover responsive agents and trigger cold-starts.

        Probes every registered agent with a test invocation.  Agents that
        respond (any status < 500) are added to the responsive pool.  Agents
        that fail all warmup attempts are excluded from measurement.

        Returns:
            (responsive_agents, elapsed_seconds)
        """
        t0 = time.monotonic()
        responsive: list[dict[str, str]] = []
        all_agents = self._scale_agents if self._scale_agents else REGISTERED_AGENTS

        for agent in all_agents:
            ok = False
            for _ in range(n_warmup):
                try:
                    payload = {
                        "jsonrpc": "2.0",
                        "method": "tasks/send",
                        "params": {"patient_id": "warmup", "encounter_id": "warmup",
                                   "clinical_data": {"chief_complaint": "warmup", "urgency": "routine", "age": 30}},
                        "id": str(uuid.uuid4()),
                    }
                    token = self._mint_jwt()
                    resp = await client.post(
                        f"{self._nexus_url}/rpc/{agent['alias']}",
                        json=payload,
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    )
                    if resp.status_code < 500:
                        ok = True
                        break
                    await asyncio.sleep(0.5)
                except Exception:
                    await asyncio.sleep(0.5)
            if ok:
                responsive.append(agent)
                logger.debug("Warmup: %s responsive", agent["alias"])
            else:
                logger.info("Warmup: %s not responsive — excluded from measurement", agent["alias"])

        elapsed = time.monotonic() - t0
        logger.info(
            "Warmup complete: %d/%d agents responsive in %.1fs",
            len(responsive), len(all_agents), elapsed,
        )
        return responsive, elapsed

    async def _run_patient_task(
        self,
        semaphore: asyncio.Semaphore,
        client: httpx.AsyncClient,
        patient: dict[str, Any],
        resolve_metrics: StepMetrics,
        invoke_metrics: StepMetrics,
    ) -> bool:
        """Execute one patient task: resolve → invoke via real services."""
        async with semaphore:
            # Pick from warmup-validated responsive agents only.
            # Falls back to full pool if warmup was skipped.
            pool = self._responsive_agents or self._scale_agents or REGISTERED_AGENTS
            agent = random.choice(pool)

            # Step 1: GHARRA resolve
            record = await self._resolve_agent(
                client, agent["agent_id"], resolve_metrics
            )
            if not record:
                return False

            # Step 2: Nexus invoke
            return await self._invoke_agent(
                client, agent["alias"], patient, invoke_metrics
            )

    async def run(
        self,
        profile: ScaleProfile = ScaleProfile.SMOKE,
        timeout: float = 300.0,
        skip_warmup: bool = False,
    ) -> SimulationReport:
        """Run the scale simulation.

        Args:
            profile: Scale profile (smoke/small/medium/large/national).
            timeout: Maximum wall-clock seconds for the simulation.
            skip_warmup: If True, skip warmup phase (for raw latency tests).

        Returns:
            SimulationReport with per-step metrics, P95/P99, throughput,
            and deployment context metadata.
        """
        config = SCALE_CONFIGS[profile]
        num_patients = config["patients"]
        num_hospitals = config["hospitals"]
        concurrency = config["concurrency"]

        # Register all scale agents in GHARRA before starting load.
        # Every agent maps to a real Nexus on-demand gateway process.
        self._scale_agents = await self._register_scale_agents()

        report = SimulationReport(
            profile=profile.value,
            config=config,
            total_tasks=num_patients,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        resolve_metrics = StepMetrics(step="gharra_resolve")
        invoke_metrics = StepMetrics(step="nexus_invoke")
        report.steps["gharra_resolve"] = resolve_metrics
        report.steps["nexus_invoke"] = invoke_metrics

        logger.info(
            "Scale simulation starting: profile=%s patients=%d hospitals=%d concurrency=%d",
            profile.value, num_patients, num_hospitals, concurrency,
        )

        pool_limits = httpx.Limits(
            max_connections=concurrency + 50,
            max_keepalive_connections=concurrency,
        )

        async with httpx.AsyncClient(timeout=30.0, limits=pool_limits) as client:
            # ── Warmup: discover responsive agents, trigger cold-starts ──
            if not skip_warmup:
                self._responsive_agents, warmup_elapsed = await self._warmup(client)
                report.warmup_elapsed_s = warmup_elapsed
                report.warmup_agents_responsive = len(self._responsive_agents)
                report.warmup_agents_total = len(self._scale_agents)
                if not self._responsive_agents:
                    logger.warning("No responsive agents after warmup — using full pool")
                    self._responsive_agents = list(self._scale_agents)
            else:
                self._responsive_agents = list(self._scale_agents)
                report.warmup_agents_responsive = len(self._responsive_agents)
                report.warmup_agents_total = len(self._scale_agents)

            # ── Generate all patient tasks ──
            patients = [
                _generate_patient(i, random.randint(1, num_hospitals))
                for i in range(num_patients)
            ]

            semaphore = asyncio.Semaphore(concurrency)
            t0 = time.monotonic()

            tasks = [
                self._run_patient_task(
                    semaphore, client, p, resolve_metrics, invoke_metrics
                )
                for p in patients
            ]
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout,
            )

        elapsed_s = time.monotonic() - t0
        report.total_elapsed_s = elapsed_s
        report.total_success = sum(1 for r in results if r is True)
        report.total_failure = num_patients - report.total_success
        report.throughput_rps = num_patients / elapsed_s if elapsed_s > 0 else 0
        report.completed_at = datetime.now(timezone.utc).isoformat()
        report.caveats = report._default_caveats()
        report.compute_hash()

        logger.info(
            "Scale simulation complete: profile=%s success=%d/%d "
            "elapsed=%.1fs throughput=%.1f rps "
            "resolve_p99=%.1fms invoke_p99=%.1fms "
            "responsive_agents=%d/%d",
            profile.value,
            report.total_success, num_patients,
            elapsed_s, report.throughput_rps,
            resolve_metrics.p99_ms, invoke_metrics.p99_ms,
            report.warmup_agents_responsive, report.warmup_agents_total,
        )

        self._report = report
        return report

    @property
    def last_report(self) -> SimulationReport | None:
        return self._report
