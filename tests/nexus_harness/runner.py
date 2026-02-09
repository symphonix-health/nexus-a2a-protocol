"""runner.py – loads JSON scenario matrices, provides helpers for
parametrised pytest tests, and produces a JSON conformance report.
"""
from __future__ import annotations

import json
import pathlib
import os
from dataclasses import dataclass, field, asdict
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


def scenarios_for(filename: str, *, tags: list[str] | None = None, scenario_type: str | None = None) -> list[dict]:
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
        "triage-agent":       os.environ.get("ED_TRIAGE_URL",     "http://localhost:8021"),
        "diagnosis-agent":    os.environ.get("ED_DIAGNOSIS_URL",  "http://localhost:8022"),
        "openhie-mediator":   os.environ.get("ED_MEDIATOR_URL",   "http://localhost:8023"),
    },
    "telemed-scribe": {
        "transcriber-agent":  os.environ.get("SCRIBE_TRANSCRIBER_URL", "http://localhost:8031"),
        "summariser-agent":   os.environ.get("SCRIBE_SUMMARISER_URL",  "http://localhost:8032"),
        "ehr-writer-agent":   os.environ.get("SCRIBE_EHR_URL",        "http://localhost:8033"),
    },
    "consent-verification": {
        "insurer-agent":      os.environ.get("CONSENT_INSURER_URL",  "http://localhost:8041"),
        "provider-agent":     os.environ.get("CONSENT_PROVIDER_URL", "http://localhost:8042"),
        "consent-analyser":   os.environ.get("CONSENT_ANALYSER_URL", "http://localhost:8043"),
        "hitl-ui":            os.environ.get("CONSENT_HITL_URL",     "http://localhost:8044"),
    },
    "public-health-surveillance": {
        "hospital-reporter":      os.environ.get("SURV_HOSPITAL_URL",    "http://localhost:8051"),
        "osint-agent":            os.environ.get("SURV_OSINT_URL",       "http://localhost:8052"),
        "central-surveillance":   os.environ.get("SURV_CENTRAL_URL",     "http://localhost:8053"),
    },
    "command-centre": {
        "dashboard":          os.environ.get("COMMAND_CENTRE_URL", "http://localhost:8099"),
    },
}


def entry_url(demo: str) -> str:
    """Return the entry-point (orchestrator) URL for a demo."""
    urls = DEMO_URLS.get(demo, {})
    # First agent in the dict is the orchestrator by convention
    return next(iter(urls.values()), "http://localhost:8000")


# ── Conformance report ──────────────────────────────────────────────
@dataclass
class ScenarioResult:
    use_case_id: str
    scenario_title: str
    poc_demo: str
    scenario_type: str
    requirement_ids: list[str] = field(default_factory=list)
    status: str = "pending"          # pending | pass | fail | skip | error
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

    def add(self, sr: ScenarioResult):
        self.results.append(sr)
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
        return json.dumps(asdict(self), indent=indent)

    def save(self, path: str | pathlib.Path):
        pathlib.Path(path).write_text(self.to_json(), encoding="utf-8")


# Singleton report instance – collected across all test modules
_report = ConformanceReport()

def get_report() -> ConformanceReport:
    return _report
