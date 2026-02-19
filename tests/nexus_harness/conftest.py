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
    candidate_secrets = [
        os.environ.get("NEXUS_JWT_SECRET", "").strip(),
        "dev-secret-change-me",
        "super-secret-test-key-change-me",
    ]
    # Preserve order while removing blanks/duplicates.
    candidate_secrets = list(dict.fromkeys([s for s in candidate_secrets if s]))

    probe_url = os.environ.get("NEXUS_JWT_PROBE_URL", "http://localhost:8021/rpc")
    probe_payload = {
        "jsonrpc": "2.0",
        "id": "harness-auth-probe",
        "method": "method/does-not-exist",
        "params": {},
    }

    first_token = ""
    for secret in candidate_secrets:
        candidate = mint_jwt(
            "test-harness",
            secret,
            ttl_seconds=3600,
            scope=required_scope,
        )
        if not first_token:
            first_token = candidate

        try:
            with httpx.Client(timeout=2.0) as sync_client:
                resp = sync_client.post(
                    probe_url,
                    headers={
                        "Authorization": f"Bearer {candidate}",
                        "Content-Type": "application/json",
                    },
                    json=probe_payload,
                )
            if resp.status_code != 401:
                return candidate
        except Exception:
            # Probe might be unavailable in some runs; continue trying known secrets.
            continue

    token = first_token
    if not token:
        pytest.skip("Cannot obtain JWT token – no usable secret candidates")
    return token


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
