from __future__ import annotations

import json
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_backlog_document_exists_with_ticket_ids() -> None:
    backlog = REPO_ROOT / "docs" / "helixcare_protocol_refactor_backlog_2026-02-20.md"
    assert backlog.exists(), f"Missing backlog document: {backlog}"
    text = backlog.read_text(encoding="utf-8")
    for ticket in ("P0-001", "P0-002", "P0-003", "P1-001"):
        assert ticket in text


def test_harness_tests_do_not_use_hardcoded_slice_limits() -> None:
    harness_dir = REPO_ROOT / "tests" / "nexus_harness"
    offenders: list[str] = []
    parametrize_pattern = re.compile(r"@pytest\.mark\.parametrize\([^\n]*\[:\d+\]")
    scenario_assign_pattern = re.compile(r"_(positive|negative|edge)\s*=\s*[^\n]*\[:\d+\]")
    for path in sorted(harness_dir.glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        if parametrize_pattern.search(text) or scenario_assign_pattern.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"Hardcoded scenario slicing remains: {offenders}"


def test_public_health_agent_cards_have_protocol_and_methods_contract() -> None:
    cards = [
        REPO_ROOT / "demos" / "public-health-surveillance" / "central-surveillance" / "agent_card.json",
        REPO_ROOT / "demos" / "public-health-surveillance" / "hospital-reporter" / "agent_card.json",
        REPO_ROOT / "demos" / "public-health-surveillance" / "osint-agent" / "agent_card.json",
    ]
    required = {"name", "protocol", "protocolVersion", "methods", "authentication", "capabilities"}
    for path in cards:
        payload = json.loads(path.read_text(encoding="utf-8"))
        missing = sorted(required - set(payload.keys()))
        assert not missing, f"{path}: missing keys {missing}"
        methods = payload.get("methods", [])
        assert isinstance(methods, list), f"{path}: methods must be a list"
        assert "tasks/resubscribe" in methods, f"{path}: missing tasks/resubscribe declaration"


def test_runtime_wiring_contains_resubscribe_handlers() -> None:
    generic_runtime = (
        REPO_ROOT / "shared" / "nexus_common" / "generic_demo_agent.py"
    ).read_text(encoding="utf-8")
    triage_runtime = (
        REPO_ROOT / "demos" / "ed-triage" / "triage-agent" / "app" / "main.py"
    ).read_text(encoding="utf-8")
    assert '"tasks/resubscribe": _tasks_resubscribe' in generic_runtime
    assert 'METHODS["tasks/resubscribe"] = _tasks_resubscribe' in triage_runtime


def test_harness_negative_assertions_use_deterministic_error_contract() -> None:
    harness_dir = REPO_ROOT / "tests" / "nexus_harness"
    helixcare_files = sorted(harness_dir.glob("test_helixcare_*.py"))
    offenders: list[str] = []
    for path in helixcare_files:
        text = path.read_text(encoding="utf-8")
        if "assert_deterministic_negative_rpc(" not in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "HelixCare harness negatives must call assert_deterministic_negative_rpc: "
        f"{offenders}"
    )
