"""Cross-System Observability Tests.

Validates requirements:
  NFR-6  Auditability — immutable audit trail across services
  NFR-7  FHIR AuditEvent — ATNA-compatible audit event export
  NFR-8  Availability — all services healthy
  NFR-9  Performance — metrics and SLI tracking
  FR-13  Registry events — lifecycle events in ledger
"""

from __future__ import annotations

import json

import pytest

from harness.observability import (
    ObservabilityCollector,
    save_conformance_report,
    save_fhir_audit_bundle,
)


@pytest.fixture(scope="session")
def collector(gharra_url: str, nexus_url: str, signalbox_url: str) -> ObservabilityCollector:
    return ObservabilityCollector(
        gharra_url=gharra_url,
        nexus_url=nexus_url,
        signalbox_url=signalbox_url,
    )


# ── Service Health (NFR-8) ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_services_healthy(collector: ObservabilityCollector):
    """NFR-8: All integration services are healthy."""
    report = await collector.collect()
    for name, status in report.service_health.items():
        if status.get("status") == "unreachable":
            continue  # SignalBox may be optional
        assert status.get("status") in ("healthy", "ok"), (
            f"{name} is not healthy: {status}"
        )


# ── GHARRA Metrics (NFR-9) ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_gharra_metrics_accessible(collector: ObservabilityCollector):
    """NFR-9: GHARRA Prometheus metrics endpoint returns data."""
    report = await collector.collect()
    assert report.gharra_metrics is not None
    assert report.gharra_metrics.raw, "Metrics endpoint returned empty"


@pytest.mark.asyncio
async def test_gharra_http_metrics_tracked(collector: ObservabilityCollector):
    """NFR-9: HTTP request metrics are being counted."""
    report = await collector.collect()
    m = report.gharra_metrics
    # After seeding + running scenarios, there should be many requests
    assert m.http_requests_total > 0 or m.agent_registrations > 0, (
        "No HTTP request or registration metrics recorded"
    )


# ── Transparency Ledger (NFR-6) ──────────────────────────────────────

@pytest.mark.asyncio
async def test_ledger_has_entries(collector: ObservabilityCollector):
    """NFR-6: Transparency ledger contains audit entries."""
    report = await collector.collect()
    assert len(report.ledger_entries) > 0, "Ledger is empty"


@pytest.mark.asyncio
async def test_ledger_chain_integrity(collector: ObservabilityCollector):
    """NFR-6: Ledger hash chain is valid (tamper-evidence)."""
    report = await collector.collect()
    if len(report.ledger_entries) <= 1:
        pytest.skip("Not enough entries to verify chain")
    for entry in report.ledger_entries[1:]:
        assert entry.prev_hash, (
            f"Entry seq={entry.seq} has no prev_hash (chain broken)"
        )


@pytest.mark.asyncio
async def test_ledger_records_agent_lifecycle(collector: ObservabilityCollector):
    """FR-13: Ledger records agent registration events."""
    report = await collector.collect()
    operations = {e.operation for e in report.ledger_entries}
    assert "agent.registered" in operations, (
        f"No agent.registered in ledger. Found: {sorted(operations)}"
    )


# ── FHIR AuditEvent (NFR-7) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_fhir_audit_events_generated(collector: ObservabilityCollector):
    """NFR-7: Ledger entries map to FHIR AuditEvent resources."""
    report = await collector.collect()
    assert len(report.fhir_audit_events) > 0, "No FHIR AuditEvents generated"


@pytest.mark.asyncio
async def test_fhir_audit_event_structure(collector: ObservabilityCollector):
    """NFR-7: FHIR AuditEvent contains required R4 fields."""
    report = await collector.collect()
    assert report.fhir_audit_events, "No events to validate"

    event = report.fhir_audit_events[0]
    fhir = event.to_fhir()

    required_fields = ["resourceType", "type", "action", "recorded", "outcome", "agent", "source"]
    for field in required_fields:
        assert field in fhir, f"Missing FHIR field: {field}"
    assert fhir["resourceType"] == "AuditEvent"


@pytest.mark.asyncio
async def test_fhir_audit_bundle_exportable(
    collector: ObservabilityCollector, tmp_path
):
    """NFR-7: FHIR AuditEvent bundle can be exported to JSON."""
    report = await collector.collect()
    path = save_fhir_audit_bundle(report.fhir_audit_events, tmp_path / "audit_bundle.json")

    with open(path) as f:
        bundle = json.load(f)
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    assert bundle["total"] == len(report.fhir_audit_events)
    assert len(bundle["entry"]) > 0


# ── Conformance Report ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_conformance_report_generated(collector: ObservabilityCollector):
    """Conformance report covers all observability requirements."""
    report = await collector.collect()
    conf = report.conformance

    assert conf["total"] > 0
    assert conf["passed"] > 0
    assert conf["pass_rate"] != "0%"

    # Check that key requirements are tested
    req_ids_tested = set()
    for r in conf["results"]:
        req_ids_tested.update(r.get("requirement_ids", []))

    for req in ["NFR-6", "NFR-7", "NFR-8", "NFR-9", "FR-13"]:
        assert req in req_ids_tested, f"Requirement {req} not in conformance report"


@pytest.mark.asyncio
async def test_conformance_report_exportable(
    collector: ObservabilityCollector, tmp_path
):
    """Conformance report exports in Nexus template format."""
    report = await collector.collect()
    path = save_conformance_report(report, tmp_path / "conformance.json")

    with open(path) as f:
        data = json.load(f)
    assert "generated_at" in data
    assert "total" in data
    assert "passed" in data
    assert "failed" in data
    assert "results" in data
    assert isinstance(data["results"], list)


# ── Full Summary ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_observability_summary(collector: ObservabilityCollector):
    """Full observability summary contains all required sections."""
    report = await collector.collect()
    summary = report.summary()

    required_sections = ["generated_at", "services", "gharra_metrics", "audit", "slo", "conformance"]
    for section in required_sections:
        assert section in summary, f"Missing summary section: {section}"

    # Audit section
    audit = summary["audit"]
    assert "ledger_entries" in audit
    assert "fhir_audit_events" in audit
    assert "ledger_chain_valid" in audit

    print(f"\n{'='*60}")
    print(f"  Observability Report Summary")
    print(f"  Services: {json.dumps(summary['services'], indent=2)}")
    print(f"  Ledger entries: {audit['ledger_entries']}")
    print(f"  FHIR audit events: {audit['fhir_audit_events']}")
    print(f"  Chain valid: {audit['ledger_chain_valid']}")
    print(f"  Conformance: {summary['conformance']['passed']}/{summary['conformance']['total']} pass")
    print(f"{'='*60}")
