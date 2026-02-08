"""Shared fixtures for the nexus-harness test suite."""
from __future__ import annotations

import os
import pathlib
import pytest
import pytest_asyncio
import httpx

from tests.nexus_harness.runner import get_report


# ── JWT token fixture ───────────────────────────────────────────────
@pytest.fixture(scope="session")
def jwt_token() -> str:
    """Return a JWT token for authenticating against demo agents."""
    token = os.environ.get("NEXUS_JWT_TOKEN", "")
    if not token:
        # Try to mint one from secret
        secret = os.environ.get("NEXUS_JWT_SECRET", "super-secret-test-key-change-me")
        try:
            import sys
            sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "shared"))
            from nexus_common.auth import mint_jwt
            token = mint_jwt("test-harness", secret, ttl_seconds=3600)
        except Exception as exc:
            pytest.skip(f"Cannot obtain JWT token – set NEXUS_JWT_TOKEN or NEXUS_JWT_SECRET ({exc})")
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
