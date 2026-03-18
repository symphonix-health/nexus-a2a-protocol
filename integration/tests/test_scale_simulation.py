"""Large-Scale Agent Simulation Tests.

Validates that the integration chain handles national-scale workloads:
  - Tasks flow through GHARRA resolution → Nexus routing → real agents
  - Concurrent patient workflows execute without cascading failures
  - Latency stays within SLA bounds (P99 < 5s for smoke/small)
  - Error rates stay below acceptable thresholds
  - Reports include deployment context metadata for governance

Scale profiles:
  smoke:     10 patients, 2 hospitals, 1 insurer, 5 concurrent
  small:     100 patients, 10 hospitals, 5 insurers, 20 concurrent
  medium:    1,000 patients, 50 hospitals, 10 insurers, 50 concurrent
  large:     10,000 patients, 500 hospitals, 100 insurers, 100 concurrent
  national:  100,000 patients, 2,000 hospitals, 500 insurers, 250 concurrent
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.scale_simulation import ScaleProfile, ScaleSimulator


@pytest.fixture(scope="session")
def simulator(gharra_url: str, nexus_url: str) -> ScaleSimulator:
    return ScaleSimulator(gharra_url=gharra_url, nexus_url=nexus_url)


@pytest.fixture(scope="session")
def reports_dir() -> Path:
    """Ensure the reports directory exists."""
    d = Path(__file__).resolve().parent.parent / "reports"
    d.mkdir(exist_ok=True)
    return d


# ── Smoke: 10 patients ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scale_smoke(simulator: ScaleSimulator):
    """Smoke test: 10 patients through GHARRA → Nexus → agents.

    After warmup discovers responsive agents, 80%+ of tasks should succeed.
    """
    report = await simulator.run(ScaleProfile.SMOKE)

    assert report.total_tasks == 10
    assert report.total_success > 0, f"No tasks succeeded: {report.summary()}"
    # With warmup filtering, 80% of tasks against responsive agents should succeed
    assert report.total_success >= report.total_tasks * 0.8, (
        f"Too many failures: {report.total_failure}/{report.total_tasks} "
        f"(responsive agents: {report.warmup_agents_responsive}/{report.warmup_agents_total})"
    )

    # GHARRA resolution should work for all (resolution doesn't depend on Nexus agent existence)
    resolve = report.steps["gharra_resolve"]
    assert resolve.success == report.total_tasks, (
        f"GHARRA resolve failures: {resolve.failure}/{resolve.count}"
    )

    summary = report.summary()
    assert summary["throughput_rps"] > 0


@pytest.mark.asyncio
async def test_scale_smoke_latency(simulator: ScaleSimulator):
    """Smoke latency: GHARRA resolve P99 under 2 seconds."""
    report = await simulator.run(ScaleProfile.SMOKE)

    resolve = report.steps["gharra_resolve"]
    assert resolve.p99_ms < 2000, (
        f"GHARRA resolve P99 too high: {resolve.p99_ms:.0f}ms"
    )


# ── Small: 100 patients ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scale_small(simulator: ScaleSimulator):
    """Small scale: 100 patients, 20 concurrent."""
    report = await simulator.run(ScaleProfile.SMALL)

    assert report.total_tasks == 100
    resolve = report.steps["gharra_resolve"]
    assert resolve.error_rate < 0.05, (
        f"GHARRA resolve error rate too high: {resolve.error_rate:.2%}"
    )

    summary = report.summary()
    assert summary["throughput_rps"] > 1, (
        f"Throughput too low: {summary['throughput_rps']} rps"
    )


@pytest.mark.asyncio
async def test_scale_small_metrics(simulator: ScaleSimulator):
    """Small scale: verify metrics collection completeness."""
    report = await simulator.run(ScaleProfile.SMALL)

    # GHARRA resolve should always be called for all patients
    resolve = report.steps["gharra_resolve"]
    assert resolve.count == 100, f"gharra_resolve count mismatch: {resolve.count}"
    assert resolve.avg_ms > 0, "gharra_resolve avg_ms should be > 0"
    assert resolve.p95_ms > 0, "gharra_resolve p95 should be > 0"
    assert resolve.p99_ms >= resolve.p95_ms, (
        f"gharra_resolve p99 ({resolve.p99_ms}) < p95 ({resolve.p95_ms})"
    )

    # Nexus invoke count may be <= 100 (skipped when resolve fails),
    # but should be close to 100 with healthy GHARRA
    invoke = report.steps["nexus_invoke"]
    assert invoke.count > 0, "nexus_invoke count should be > 0"
    assert invoke.avg_ms > 0, "nexus_invoke avg_ms should be > 0"


# ── Medium: 1,000 patients ────────────────────────────────────────────

@pytest.mark.slow
@pytest.mark.asyncio
async def test_scale_medium(simulator: ScaleSimulator):
    """Medium scale: 1,000 patients, 50 concurrent.

    This is the minimum for validating that the system handles
    sustained concurrent load without cascading failures.
    """
    report = await simulator.run(ScaleProfile.MEDIUM, timeout=120.0)

    assert report.total_tasks == 1_000
    resolve = report.steps["gharra_resolve"]
    invoke = report.steps["nexus_invoke"]

    # GHARRA resolution must be 100% reliable
    assert resolve.error_rate == 0, (
        f"GHARRA resolve error rate: {resolve.error_rate:.2%}"
    )

    # Nexus invocation: 100% with retry on cold-start 503s
    assert invoke.error_rate == 0, (
        f"Nexus invoke error rate: {invoke.error_rate:.2%} "
        f"({invoke.failure} failures out of {invoke.count})"
    )

    # Overall throughput should sustain > 5 rps
    assert report.throughput_rps > 5, (
        f"Throughput collapsed: {report.throughput_rps:.1f} rps"
    )

    summary = report.summary()
    print(f"\n{'='*60}")
    print(f"  Medium scale simulation results")
    print(f"  Patients: {summary['total_tasks']}")
    print(f"  Success: {summary['success']}, Failure: {summary['failure']}")
    print(f"  Throughput: {summary['throughput_rps']} rps")
    print(f"  Resolve P99: {resolve.p99_ms:.0f}ms")
    print(f"  Invoke P99: {invoke.p99_ms:.0f}ms")
    print(f"{'='*60}")


# ── Large: 10,000 patients ─────────────────────────────────────────────

@pytest.mark.slow
@pytest.mark.asyncio
async def test_scale_large(simulator: ScaleSimulator):
    """Large scale: 10,000 patients, 500 hospitals, 100 concurrent.

    Simulates a national workload: 10K patients across 500 hospitals
    with 100 insurers, flowing through GHARRA → Nexus → real agents.
    """
    report = await simulator.run(ScaleProfile.LARGE, timeout=300.0)

    assert report.total_tasks == 10_000
    resolve = report.steps["gharra_resolve"]
    invoke = report.steps["nexus_invoke"]

    # 100% GHARRA resolution
    assert resolve.error_rate == 0, (
        f"GHARRA resolve error rate: {resolve.error_rate:.2%}"
    )

    # 100% Nexus invocation with retry
    assert invoke.error_rate == 0, (
        f"Nexus invoke error rate: {invoke.error_rate:.2%} "
        f"({invoke.failure} failures out of {invoke.count})"
    )

    # Throughput
    assert report.throughput_rps > 20, (
        f"Throughput too low: {report.throughput_rps:.1f} rps"
    )

    summary = report.summary()
    print(f"\n{'='*60}")
    print(f"  Large scale simulation results")
    print(f"  Patients: {summary['total_tasks']}")
    print(f"  Success: {summary['success']}, Failure: {summary['failure']}")
    print(f"  Throughput: {summary['throughput_rps']} rps")
    print(f"  Resolve P99: {resolve.p99_ms:.0f}ms")
    print(f"  Invoke P99: {invoke.p99_ms:.0f}ms")
    print(f"  Elapsed: {summary['elapsed_s']}s")
    print(f"{'='*60}")


# ── Report structure ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_structure(simulator: ScaleSimulator):
    """Report contains all required observability fields."""
    report = await simulator.run(ScaleProfile.SMOKE)
    summary = report.summary()

    required_keys = [
        "profile", "config", "total_tasks", "success",
        "failure", "error_rate", "elapsed_s", "throughput_rps", "steps",
    ]
    for key in required_keys:
        assert key in summary, f"Missing report key: {key}"

    for step_name in ("gharra_resolve", "nexus_invoke"):
        step = summary["steps"][step_name]
        for metric in ("count", "success", "failure", "avg_ms",
                       "p95_ms", "p99_ms", "min_ms", "max_ms", "error_rate"):
            assert metric in step, f"Missing {step_name} metric: {metric}"


# ── Report metadata (Sprint 1 additions) ──────────────────────────────

@pytest.mark.asyncio
async def test_report_metadata(simulator: ScaleSimulator):
    """Report includes deployment context, infrastructure, and caveats."""
    report = await simulator.run(ScaleProfile.SMOKE)
    summary = report.summary()

    # Deployment context
    assert "deployment_context" in summary
    assert summary["deployment_context"] in ("docker_local", "cloud_single_region", "cloud_multi_region")

    # Infrastructure
    assert "infrastructure" in summary
    infra = summary["infrastructure"]
    assert "cpu_count" in infra
    assert "platform" in infra
    assert "python_version" in infra

    # Timestamps
    assert "started_at" in summary
    assert "completed_at" in summary
    assert summary["started_at"] != ""
    assert summary["completed_at"] != ""

    # Warmup
    assert "warmup_elapsed_s" in summary
    assert "warmup_agents_responsive" in summary
    assert "warmup_agents_total" in summary
    assert summary["warmup_agents_responsive"] > 0, "No responsive agents after warmup"

    # Caveats (mandatory for governance)
    assert "caveats" in summary
    assert len(summary["caveats"]) > 0, "Report must include caveats"

    # Report hash
    assert "report_hash" in summary
    assert len(summary["report_hash"]) == 64, "report_hash must be SHA-256 (64 hex chars)"


@pytest.mark.asyncio
async def test_report_saved(simulator: ScaleSimulator, reports_dir: Path):
    """Report can be saved to disk as JSON."""
    report = await simulator.run(ScaleProfile.SMOKE)
    path = report.save(reports_dir / "scale_simulation_smoke.json")

    assert path.exists()
    data = json.loads(path.read_text())
    assert data["profile"] == "smoke"
    assert data["report_hash"] != ""
    assert data["deployment_context"] == "docker_local"
    assert len(data["caveats"]) > 0


@pytest.mark.asyncio
async def test_report_hash_deterministic(simulator: ScaleSimulator):
    """Report hash is deterministic for the same report data."""
    report = await simulator.run(ScaleProfile.SMOKE)
    hash1 = report.compute_hash()
    hash2 = report.compute_hash()
    assert hash1 == hash2, "Same report must produce same hash"
