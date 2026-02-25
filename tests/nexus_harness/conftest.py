"""Shared fixtures for the nexus-harness test suite."""

from __future__ import annotations

import os
import pathlib

import httpx
import pytest
import pytest_asyncio

from tests.nexus_harness.runner import get_report


# ── JWT token fixture ───────────────────────────────────────────────
@pytest.fixture(scope="session")
def jwt_token() -> str:
    """Return a JWT token for authenticating against demo agents."""
    token = os.environ.get("NEXUS_JWT_TOKEN", "")
    if token:
        return token

    try:
        import sys

        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "shared"))
        from nexus_common.auth import mint_jwt
    except Exception as exc:
        pytest.skip(f"Cannot obtain JWT token – set NEXUS_JWT_TOKEN or NEXUS_JWT_SECRET ({exc})")

    required_scope = os.environ.get("NEXUS_REQUIRED_SCOPE", "nexus:invoke")
    env_secret = os.environ.get("NEXUS_JWT_SECRET", "").strip()
    # Prefer launcher default first for deterministic local runs,
    # then env/legacy fallback.
    candidate_secrets = [
        "dev-secret-change-me",
        env_secret,
        "super-secret-test-key-change-me",
    ]
    # Preserve order while removing blanks/duplicates.
    candidate_secrets = list(dict.fromkeys([s for s in candidate_secrets if s]))

    triage_base = os.environ.get("ED_TRIAGE_URL", "http://localhost:8021")
    diagnosis_base = os.environ.get(
        "ED_DIAGNOSIS_URL",
        "http://localhost:8022",
    )
    mediator_base = os.environ.get(
        "ED_MEDIATOR_URL",
        "http://localhost:8023",
    )
    probe_urls = [
        os.environ.get("NEXUS_JWT_PROBE_URL", "").strip(),
        f"{triage_base.rstrip('/')}/rpc",
        f"{diagnosis_base.rstrip('/')}/rpc",
        f"{mediator_base.rstrip('/')}/rpc",
    ]
    probe_urls = list(dict.fromkeys([u for u in probe_urls if u]))

    probe_payload = {
        "jsonrpc": "2.0",
        "id": "harness-auth-probe",
        "method": "method/does-not-exist",
        "params": {},
    }

    # Try for a short bounded window to avoid races with local service startup.
    startup_attempts = int(os.environ.get("NEXUS_JWT_PROBE_ATTEMPTS", "12"))
    startup_sleep_s = float(os.environ.get("NEXUS_JWT_PROBE_SLEEP_SECONDS", "1.0"))

    with httpx.Client(timeout=2.0) as sync_client:
        for _ in range(startup_attempts):
            for secret in candidate_secrets:
                candidate = mint_jwt(
                    "test-harness",
                    secret,
                    ttl_seconds=3600,
                    scope=required_scope,
                )
                for probe_url in probe_urls:
                    try:
                        resp = sync_client.post(
                            probe_url,
                            headers={
                                "Authorization": f"Bearer {candidate}",
                                "Content-Type": "application/json",
                            },
                            json=probe_payload,
                        )
                        # Any non-401 means signature+scope were accepted.
                        if resp.status_code != 401:
                            return candidate
                    except Exception:
                        continue

            import time as _time

            _time.sleep(startup_sleep_s)

    # Deterministic local fallback when probes are unavailable.
    if not candidate_secrets:
        pytest.skip("Cannot obtain JWT token – no usable secret candidates")
    return mint_jwt(
        "test-harness",
        "dev-secret-change-me",
        ttl_seconds=3600,
        scope=required_scope,
    )


# ── Async HTTP client ──────────────────────────────────────────────
@pytest.fixture(scope="session")
def auth_headers(jwt_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }


@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(timeout=30.0) as c:
        yield c


# ── Save conformance report at session end ─────────────────────────
@pytest.fixture(scope="session", autouse=True)
def _save_report(tmp_path_factory):
    yield
    report = get_report()
    out = pathlib.Path(__file__).resolve().parents[2] / "docs" / "conformance-report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    report.save(out)
    report.save(out)
