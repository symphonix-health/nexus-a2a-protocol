"""Shared pytest fixtures for the integration harness.

These fixtures connect to the real running services started by docker-compose.
No mocks — every call hits the actual GHARRA, Nexus, and SignalBox instances.
"""

from __future__ import annotations

import logging
import os
import sys
import time

import httpx
import pytest

# Ensure the integration package is importable
sys.path.insert(0, os.path.dirname(__file__))

from harness.gharra_resolver import GharraResolver
from harness.nexus_connector import NexusConnector
from harness.signalbox_driver import SignalBoxDriver
from harness.workflow_runner import WorkflowRunner
from harness.seed import seed_gharra, seed_sovereign_gb, seed_sovereign_us, AGENTS, GB_AGENTS, US_AGENTS

logger = logging.getLogger("integration.conftest")


# ── Service URLs (overridable via env vars) ─────────────────────────────

GHARRA_URL = os.getenv("GHARRA_BASE_URL", "http://localhost:8400")
GHARRA_GB_URL = os.getenv("GHARRA_GB_BASE_URL", "http://localhost:8401")
GHARRA_US_URL = os.getenv("GHARRA_US_BASE_URL", "http://localhost:8402")
NEXUS_URL = os.getenv("NEXUS_GATEWAY_URL", "http://localhost:8100")
SIGNALBOX_URL = os.getenv("SIGNALBOX_BASE_URL", "http://localhost:8221")

# Maximum time to wait for services before failing tests (seconds)
SERVICE_WAIT_TIMEOUT = int(os.getenv("SERVICE_WAIT_TIMEOUT", "60"))


# ── Service readiness ──────────────────────────────────────────────────

def wait_for_services(
    gharra_url: str,
    nexus_url: str,
    gharra_gb_url: str = "",
    gharra_us_url: str = "",
    timeout: int = SERVICE_WAIT_TIMEOUT,
) -> None:
    """Block until GHARRA instances and Nexus health endpoints respond.

    Polls /health on all services with 2-second intervals.  If any
    service fails to respond within *timeout* seconds, raises a clear
    error with the last status so the CI log is actionable.
    """
    services = {
        "GHARRA (root)": f"{gharra_url}/health",
        "Nexus":  f"{nexus_url}/health",
    }
    # Add sovereign registries if URLs are provided
    if gharra_gb_url:
        services["GHARRA (GB)"] = f"{gharra_gb_url}/health"
    if gharra_us_url:
        services["GHARRA (US)"] = f"{gharra_us_url}/health"
    deadline = time.monotonic() + timeout

    for name, url in services.items():
        last_error: str | None = None
        while time.monotonic() < deadline:
            try:
                resp = httpx.get(url, timeout=5.0)
                if resp.status_code < 500:
                    logger.info("%s healthy at %s (status %d)", name, url, resp.status_code)
                    break
                last_error = f"HTTP {resp.status_code}"
            except httpx.ConnectError:
                last_error = "connection refused"
            except Exception as exc:
                last_error = str(exc)
            time.sleep(2)
        else:
            pytest.fail(
                f"{name} not ready after {timeout}s at {url} "
                f"(last error: {last_error}).  "
                f"Start services with: docker compose up -d"
            )


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def gharra_url() -> str:
    return GHARRA_URL


@pytest.fixture(scope="session")
def gharra_gb_url() -> str:
    return GHARRA_GB_URL


@pytest.fixture(scope="session")
def gharra_us_url() -> str:
    return GHARRA_US_URL


@pytest.fixture(scope="session")
def nexus_url() -> str:
    return NEXUS_URL


@pytest.fixture(scope="session")
def signalbox_url() -> str:
    return SIGNALBOX_URL


@pytest.fixture(scope="session", autouse=True)
def _wait_for_services(gharra_url: str, nexus_url: str, gharra_gb_url: str, gharra_us_url: str) -> None:
    """Wait for all GHARRA instances and Nexus to be healthy before any tests run."""
    wait_for_services(gharra_url, nexus_url, gharra_gb_url, gharra_us_url)


@pytest.fixture(scope="session")
def gharra(gharra_url: str) -> GharraResolver:
    return GharraResolver(base_url=gharra_url)


@pytest.fixture(scope="session")
def nexus(nexus_url: str) -> NexusConnector:
    return NexusConnector(gateway_url=nexus_url)


@pytest.fixture(scope="session")
def signalbox_available(signalbox_url: str) -> bool:
    """Check if SignalBox is running."""
    import httpx
    try:
        resp = httpx.get(f"{signalbox_url}/health", timeout=3.0)
        return resp.status_code < 500
    except Exception:
        return False


@pytest.fixture(scope="session")
def signalbox(signalbox_url: str, signalbox_available: bool) -> SignalBoxDriver:
    if not signalbox_available:
        pytest.skip("SignalBox not running (start with --profile signalbox)")
    return SignalBoxDriver(base_url=signalbox_url)


@pytest.fixture(scope="session")
def workflow_runner(
    gharra: GharraResolver,
    nexus: NexusConnector,
    signalbox_url: str,
    signalbox_available: bool,
) -> WorkflowRunner:
    sb = SignalBoxDriver(base_url=signalbox_url) if signalbox_available else None
    return WorkflowRunner(gharra=gharra, nexus=nexus, signalbox=sb)


@pytest.fixture(scope="session", autouse=True)
def seed_registry(gharra_url: str, gharra_gb_url: str, gharra_us_url: str) -> dict[str, str]:
    """Seed all GHARRA instances with canonical test agents before any tests run.

    Root registry (IE) gets all agents. Sovereign registries get
    jurisdiction-specific agents for cross-border federation testing.
    """
    ids: dict[str, str] = {}
    ids.update(seed_gharra(gharra_url))
    ids.update(seed_sovereign_gb(gharra_gb_url))
    ids.update(seed_sovereign_us(gharra_us_url))
    logger.info("Seeded all registries — %d total entities", len(ids))
    return ids


@pytest.fixture
def canonical_agents() -> list[dict]:
    """Return the canonical agent definitions used for seeding."""
    return list(AGENTS)


@pytest.fixture
def gb_agents() -> list[dict]:
    """Return GB sovereign agent definitions."""
    return list(GB_AGENTS)


@pytest.fixture
def us_agents() -> list[dict]:
    """Return US sovereign agent definitions."""
    return list(US_AGENTS)


@pytest.fixture
def triage_agent_id() -> str:
    return "gharra://ie/agents/triage-e2e"


@pytest.fixture
def referral_agent_id() -> str:
    return "gharra://gb/agents/referral-e2e"


@pytest.fixture
def radiology_agent_id() -> str:
    return "gharra://us/agents/radiology-e2e"


@pytest.fixture
def pathology_agent_id() -> str:
    return "gharra://de/agents/pathology-e2e"
