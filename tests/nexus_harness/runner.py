"""runner.py – loads JSON scenario matrices, provides helpers for
parametrised pytest tests, and produces a JSON conformance report.
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

# ── Matrix loader ───────────────────────────────────────────────────
MATRICES_DIR = pathlib.Path(__file__).resolve().parents[2] / "nexus-a2a" / "artefacts" / "matrices"


def load_matrix(filename: str) -> list[dict]:
    """Load a JSON matrix file and return the list of scenarios."""
    path = MATRICES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Matrix not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def scenarios_for(
    filename: str, *, tags: list[str] | None = None, scenario_type: str | None = None
) -> list[dict]:
    """Load and optionally filter scenarios from a matrix file."""
    rows = load_matrix(filename)
    if scenario_type:
        rows = [r for r in rows if r.get("scenario_type") == scenario_type]
    if tags:
        tag_set = set(tags)
        rows = [r for r in rows if tag_set.intersection(r.get("test_tags", []))]
    return rows


def pytest_ids(scenarios: list[dict]) -> list[str]:
    """Generate readable pytest IDs from scenario list."""
    return [s.get("use_case_id", f"scenario-{i}") for i, s in enumerate(scenarios)]


# ── Base URLs ───────────────────────────────────────────────────────
DEMO_URLS: dict[str, dict[str, str]] = {
    "ed-triage": {
        "triage-agent": os.environ.get("ED_TRIAGE_URL", "http://localhost:8021"),
        "diagnosis-agent": os.environ.get("ED_DIAGNOSIS_URL", "http://localhost:8022"),
        "openhie-mediator": os.environ.get("ED_MEDIATOR_URL", "http://localhost:8023"),
    },
    "telemed-scribe": {
        "transcriber-agent": os.environ.get("SCRIBE_TRANSCRIBER_URL", "http://localhost:8031"),
        "summariser-agent": os.environ.get("SCRIBE_SUMMARISER_URL", "http://localhost:8032"),
        "ehr-writer-agent": os.environ.get("SCRIBE_EHR_URL", "http://localhost:8033"),
    },
    "consent-verification": {
        "insurer-agent": os.environ.get("CONSENT_INSURER_URL", "http://localhost:8041"),
        "provider-agent": os.environ.get("CONSENT_PROVIDER_URL", "http://localhost:8042"),
        "consent-analyser": os.environ.get("CONSENT_ANALYSER_URL", "http://localhost:8043"),
        "hitl-ui": os.environ.get("CONSENT_HITL_URL", "http://localhost:8044"),
    },
    "public-health-surveillance": {
        "hospital-reporter": os.environ.get("SURV_HOSPITAL_URL", "http://localhost:8051"),
        "osint-agent": os.environ.get("SURV_OSINT_URL", "http://localhost:8052"),
        "central-surveillance": os.environ.get("SURV_CENTRAL_URL", "http://localhost:8053"),
    },
    "command-centre": {
        "dashboard": os.environ.get("COMMAND_CENTRE_URL", "http://localhost:8099"),
    },
}


def entry_url(demo: str) -> str:
    """Return the entry-point (orchestrator) URL for a demo."""
    urls = DEMO_URLS.get(demo, {})
    # First agent in the dict is the orchestrator by convention
    return next(iter(urls.values()), "http://localhost:8000")


# ── Conformance report ──────────────────────────────────────────────


def _env_positive_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except Exception:
        value = default
    return max(1, value)


@dataclass
class ScenarioResult:
    use_case_id: str
    scenario_title: str
    poc_demo: str
    scenario_type: str
    requirement_ids: list[str] = field(default_factory=list)
    status: str = "pending"  # pending | pass | fail | skip | error
    message: str = ""
    duration_ms: float = 0.0


@dataclass
class ConformanceReport:
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    results: list[ScenarioResult] = field(default_factory=list)
    dropped_results: int = 0
    max_in_memory_results: int = field(
        default_factory=lambda: _env_positive_int(
            "NEXUS_CONFORMANCE_MAX_IN_MEMORY_RESULTS",
            5000,
        )
    )

    def add(self, sr: ScenarioResult):
        self.results.append(sr)

        # Memory guard for very large runs: keep recent detail rows in-memory,
        # while still preserving aggregate counters.
        trim_threshold = self.max_in_memory_results + 256
        if len(self.results) > trim_threshold:
            to_drop = len(self.results) - self.max_in_memory_results
            self.results = self.results[to_drop:]
            self.dropped_results += to_drop

        self.total += 1
        if sr.status == "pass":
            self.passed += 1
        elif sr.status == "fail":
            self.failed += 1
        elif sr.status == "skip":
            self.skipped += 1
        else:
            self.errors += 1

    def to_json(self, indent: int = 2) -> str:
        if len(self.results) > self.max_in_memory_results:
            to_drop = len(self.results) - self.max_in_memory_results
            self.results = self.results[to_drop:]
            self.dropped_results += to_drop
        return json.dumps(asdict(self), indent=indent)

    def save(self, path: str | pathlib.Path):
        pathlib.Path(path).write_text(self.to_json(), encoding="utf-8")


# Singleton report instance – collected across all test modules
_report = ConformanceReport()


def get_report() -> ConformanceReport:
    return _report


# ── HelixCare matrix support (auto-generated) ──────────────────
HELIXCARE_MATRICES_DIR = pathlib.Path(__file__).resolve().parents[2] / "HelixCare"


def load_helixcare_matrix(filename: str) -> list[dict]:
    path = HELIXCARE_MATRICES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"HelixCare matrix not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def scenarios_for_helixcare(
    filename: str,
    *,
    tags: list[str] | None = None,
    scenario_type: str | None = None,
) -> list[dict]:
    rows = load_helixcare_matrix(filename)
    if scenario_type:
        rows = [r for r in rows if r.get("scenario_type") == scenario_type]
    if tags:
        tag_set = set(tags)
        rows = [r for r in rows if tag_set.intersection(r.get("test_tags", []))]
    return rows


HELIXCARE_URLS: dict[str, str] = {
    # Existing agents
    "triage-agent": os.environ.get("HC_TRIAGE_URL", "http://localhost:8021"),
    "diagnosis-agent": os.environ.get("HC_DIAGNOSIS_URL", "http://localhost:8022"),
    "openhie-mediator": os.environ.get("HC_MEDIATOR_URL", "http://localhost:8023"),
    "transcriber-agent": os.environ.get("HC_TRANSCRIBER_URL", "http://localhost:8031"),
    "summariser-agent": os.environ.get("HC_SUMMARISER_URL", "http://localhost:8032"),
    "ehr-writer-agent": os.environ.get("HC_EHR_URL", "http://localhost:8033"),
    "insurer-agent": os.environ.get("HC_INSURER_URL", "http://localhost:8041"),
    "provider-agent": os.environ.get("HC_PROVIDER_URL", "http://localhost:8042"),
    "consent-analyser": os.environ.get("HC_CONSENT_URL", "http://localhost:8043"),
    "hitl-ui": os.environ.get("HC_HITL_URL", "http://localhost:8044"),
    "hospital-reporter": os.environ.get("HC_HOSPITAL_URL", "http://localhost:8051"),
    "osint-agent": os.environ.get("HC_OSINT_URL", "http://localhost:8052"),
    "central-surveillance": os.environ.get("HC_CENTRAL_URL", "http://localhost:8053"),
    # HelixCare agents
    "imaging-agent": os.environ.get("HC_IMAGING_URL", "http://localhost:8024"),
    "pharmacy-agent": os.environ.get("HC_PHARMACY_URL", "http://localhost:8025"),
    "bed-manager-agent": os.environ.get("HC_BED_URL", "http://localhost:8026"),
    "discharge-agent": os.environ.get("HC_DISCHARGE_URL", "http://localhost:8027"),
    "followup-scheduler": os.environ.get("HC_FOLLOWUP_URL", "http://localhost:8028"),
    "care-coordinator": os.environ.get("HC_COORDINATOR_URL", "http://localhost:8029"),
}


AUTH_FAILURE_MODES = (
    "jwt_missing",
    "jwt_expired",
    "jwt_invalid",
    "jwt_missing_scope",
    "mtls_missing",
    "none",
    "did_fail",
    "oidc_invalid",
)


def auth_headers_for_negative_scenario(
    scenario: dict[str, Any],
    auth_headers: dict[str, str],
) -> dict[str, str]:
    """Return deterministic auth headers for matrix negative scenarios."""
    headers = dict(auth_headers)
    mode = str(scenario.get("auth_mode", "")).strip().lower()
    if any(marker in mode for marker in AUTH_FAILURE_MODES):
        # Matrix negatives currently model auth failure; omit bearer token deterministically.
        headers.pop("Authorization", None)
    return headers


def assert_deterministic_negative_rpc(
    scenario: dict[str, Any],
    *,
    status_code: int,
    body: dict[str, Any],
) -> None:
    """Validate negative RPC outcomes with explicit status and error.code/reason checks."""
    expected_result = scenario.get("expected_result", {})
    expected_error = str(expected_result.get("error") or "").strip().upper()
    expected_status_raw = scenario.get("expected_http_status")

    if expected_status_raw in (None, ""):
        expected_status = 401 if expected_error == "AUTH_FAILED" else 400
    else:
        expected_status = int(expected_status_raw)

    assert status_code == expected_status, (
        f"{scenario.get('use_case_id')}: expected HTTP {expected_status}, got {status_code}; body={body}"
    )

    assert isinstance(body, dict), (
        f"{scenario.get('use_case_id')}: expected JSON object response body, got {type(body).__name__}"
    )
    assert "error" in body, (
        f"{scenario.get('use_case_id')}: negative response must include error envelope; body={body}"
    )
    error = body.get("error")
    assert isinstance(error, dict), (
        f"{scenario.get('use_case_id')}: error payload must be object; body={body}"
    )
    code = error.get("code")
    data = error.get("data")
    reason = data.get("reason") if isinstance(data, dict) else None
    assert isinstance(code, int), (
        f"{scenario.get('use_case_id')}: error.code must be int; body={body}"
    )
    assert isinstance(reason, str) and reason.strip(), (
        f"{scenario.get('use_case_id')}: error.data.reason must be non-empty; body={body}"
    )

    auth_failure_expected = expected_error == "AUTH_FAILED" or expected_status == 401
    if auth_failure_expected:
        assert code == -32001, (
            f"{scenario.get('use_case_id')}: expected auth error.code -32001, got {code}; body={body}"
        )
        assert reason == "auth_failed", (
            f"{scenario.get('use_case_id')}: expected auth reason 'auth_failed', got '{reason}'; body={body}"
        )


def assert_clinical_negative_outcome(
    scenario: dict[str, Any],
    *,
    trace_run: dict[str, Any],
) -> None:
    """Validate clinical-handoff negatives that should block/escalate safely."""
    negative_class = str(scenario.get("negative_class", "")).strip().lower()
    assert negative_class == "clinical_handoff", (
        f"{scenario.get('use_case_id')}: expected negative_class='clinical_handoff', got '{negative_class}'"
    )
    assert isinstance(trace_run, dict), (
        f"{scenario.get('use_case_id')}: trace_run must be dict, got {type(trace_run).__name__}"
    )

    chain = trace_run.get("delegation_chain")
    assert isinstance(chain, list) and chain, (
        f"{scenario.get('use_case_id')}: expected non-empty delegation_chain"
    )
    blocked = [evt for evt in chain if evt.get("state") == "blocked_escalated"]
    assert blocked, f"{scenario.get('use_case_id')}: expected blocked_escalated event in chain"

    handover_status = str(trace_run.get("handover_contract_status", "")).strip().lower()
    assert handover_status in {"blocked", "degraded"}, (
        f"{scenario.get('use_case_id')}: expected blocked/degraded handover status, got '{handover_status}'"
    )

    expected_escalation = str(scenario.get("expected_escalation", "")).strip()
    if expected_escalation:
        observed_codes = {str(evt.get("reason_code", "")).strip() for evt in chain}
        observed_trigger = str(trace_run.get("escalation_trigger", "")).strip()
        assert expected_escalation in observed_codes or expected_escalation == observed_trigger, (
            f"{scenario.get('use_case_id')}: escalation mismatch expected '{expected_escalation}', "
            f"observed codes={sorted(observed_codes)}, trigger='{observed_trigger}'"
        )

    expected_safe_outcome = str(scenario.get("expected_safe_outcome", "")).strip().lower()
    if "hitl" in expected_safe_outcome:
        assert any(str(evt.get("escalation_target", "")).strip().lower() == "hitl_ui" for evt in chain), (
            f"{scenario.get('use_case_id')}: expected HITL escalation target"
        )
