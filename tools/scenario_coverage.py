#!/usr/bin/env python3
"""Scenario coverage utilities for HelixCare workflows.

Ensures the combined scenario suite touches every configured agent at least
once when executed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "agents.json"


_CONFIG_TO_RUNTIME_AGENT = {
    "triage_agent": "triage",
    "diagnosis_agent": "diagnosis",
    "openhie_mediator": "openhie_mediator",
    "imaging_agent": "imaging",
    "pharmacy_agent": "pharmacy",
    "bed_manager_agent": "bed_manager",
    "discharge_agent": "discharge",
    "followup_scheduler": "followup",
    "care_coordinator": "coordinator",
    "primary_care_agent": "primary_care",
    "specialty_care_agent": "specialty_care",
    "telehealth_agent": "telehealth",
    "home_visit_agent": "home_visit",
    "ccm_agent": "ccm",
    "clinician_avatar_agent": "clinician_avatar",
    "transcriber_agent": "transcriber",
    "summariser_agent": "summariser",
    "ehr_writer_agent": "ehr_writer",
    "profile_registry_agent": "profile_registry",
    "fhir_profile_agent": "fhir_profile",
    "x12_gateway_agent": "x12_gateway",
    "ncpdp_gateway_agent": "ncpdp_gateway",
    "audit_agent": "audit",
    "hl7v2_gateway_agent": "hl7v2_gateway",
    "cda_document_agent": "cda_document",
    "dicom_imaging_agent": "dicom_imaging",
}


@dataclass(frozen=True)
class CoverageReport:
    expected_agents: set[str]
    covered_agents: set[str]
    missing_agents: set[str]
    scenario_count: int


def _load_expected_runtime_agents() -> set[str]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    expected: set[str] = set()
    for group in config.get("agents", {}).values():
        if not isinstance(group, dict):
            continue
        for key in group.keys():
            expected.add(_CONFIG_TO_RUNTIME_AGENT.get(str(key), str(key)))
    return expected


def build_coverage_report(scenarios: list[Any]) -> CoverageReport:
    expected_agents = _load_expected_runtime_agents()
    covered_agents: set[str] = set()

    for scenario in scenarios:
        for step in getattr(scenario, "journey_steps", []):
            if isinstance(step, dict) and step.get("agent"):
                covered_agents.add(str(step["agent"]))

    return CoverageReport(
        expected_agents=expected_agents,
        covered_agents=covered_agents,
        missing_agents=expected_agents - covered_agents,
        scenario_count=len(scenarios),
    )


def main() -> int:
    from helixcare_scenarios import SCENARIOS, _load_additional_scenarios

    scenarios = SCENARIOS + _load_additional_scenarios()
    report = build_coverage_report(scenarios)

    print(f"scenario_count={report.scenario_count}")
    print(f"expected_agents={len(report.expected_agents)}")
    print(f"covered_agents={len(report.covered_agents)}")

    if report.missing_agents:
        print("missing_agents=" + ",".join(sorted(report.missing_agents)))
        return 1

    print("missing_agents=none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
