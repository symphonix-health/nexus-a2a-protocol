"""Seed GHARRA with canonical e2e test agents.

This module reuses the exact same agent records defined in the GHARRA
repository's ``tests/e2e/conftest.py::seed_full_scenario()``.  No synthetic
data is introduced — every record mirrors what the GHARRA test suite
already validates.

Can run standalone (``python seed.py``) or be imported by tests.
"""

from __future__ import annotations

import os
import sys
import uuid
import logging

import httpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger("harness.seed")

GHARRA_BASE_URL = os.getenv("GHARRA_BASE_URL", "http://localhost:8400")
GHARRA_GB_BASE_URL = os.getenv("GHARRA_GB_BASE_URL", "http://localhost:8401")
GHARRA_US_BASE_URL = os.getenv("GHARRA_US_BASE_URL", "http://localhost:8402")


def _idem() -> str:
    return str(uuid.uuid4())


# ── Canonical agent records (from global-agent-registry/tests/e2e/conftest.py)

REGISTRIES = [
    {
        "display_name": "GHARRA Root",
        "jurisdiction": "IE",
        "tier": "root",
        "api_base_url": "http://gharra:8400",
    },
    {
        "display_name": "NHS Sovereign",
        "jurisdiction": "GB",
        "tier": "sovereign",
        "api_base_url": "https://nhs.sovereign.gharra.io",
    },
    {
        "display_name": "St James Hospital",
        "jurisdiction": "IE",
        "tier": "organisational",
        "api_base_url": "https://stjames.org.gharra.io",
    },
]

AGENTS = [
    # IE triage agent — nexus-a2a-jsonrpc, dual-endpoint, full trust
    {
        "agent_id": "gharra://ie/agents/triage-e2e",
        "display_name": "Triage Agent",
        "jurisdiction": "IE",
        "did_uri": "did:web:gharra.health:ie:agents:triage-e2e",
        "organisation_lei": "635400LNPK21HAK3CH18",
        "endpoints": [
            {
                "url": "http://nexus-gateway:8100/rpc/triage",
                "protocol": "nexus-a2a-jsonrpc",
                "region": "eu-west-1",
                "priority": 10,
                "weight": 100,
            },
        ],
        "capabilities": {
            "protocols": ["nexus-a2a-jsonrpc", "fhir-r4"],
            "fhir_r4": True,
            "stream_resume": True,
        },
        "trust": {
            "jwks_uri": "https://triage.ie/.well-known/jwks.json",
            "mtls_required": True,
            "token_binding": "dpop",
            "cert_thumbprints": ["sha256:abc123"],
        },
        "policy_tags": {
            "residency": ["EU"],
            "phi_allowed": False,
            "data_classification": "confidential",
            "purpose_of_use": ["treatment"],
        },
        "attestations": [
            {
                "type": "ISO27001",
                "issuer": "BSI",
                "issued_at": "2025-06-01T00:00:00Z",
                "expires_at": "2026-04-01T00:00:00Z",
                "claims": {},
            }
        ],
    },
    # GB referral agent — http-rest
    {
        "agent_id": "gharra://gb/agents/referral-e2e",
        "display_name": "Referral Agent",
        "jurisdiction": "GB",
        "did_uri": "did:web:gharra.health:gb:agents:referral-e2e",
        "organisation_lei": "213800WSGIIZCXF1P572",
        "endpoints": [
            {
                "url": "http://nexus-gateway:8100/rpc/diagnosis",
                "protocol": "http-rest",
                "region": "eu-west-2",
                "priority": 20,
                "weight": 100,
            }
        ],
        "capabilities": {
            "protocols": ["http-rest", "fhir-r4"],
            "fhir_r4": True,
        },
        "policy_tags": {
            "residency": ["GB", "EU"],
            "phi_allowed": True,
            "data_classification": "restricted",
            "purpose_of_use": ["treatment", "research"],
        },
    },
    # US radiology agent — http-rest, dual-endpoint
    {
        "agent_id": "gharra://us/agents/radiology-e2e",
        "display_name": "Radiology AI",
        "jurisdiction": "US",
        "did_uri": "did:web:gharra.health:us:agents:radiology-e2e",
        "organisation_lei": "549300EX04Q2QBFQTQ27",
        "endpoints": [
            {
                "url": "http://nexus-gateway:8100/rpc/imaging",
                "protocol": "http-rest",
                "region": "us-east-1",
                "priority": 10,
                "weight": 100,
            },
            {
                "url": "http://nexus-gateway:8100/rpc/imaging",
                "protocol": "http-rest",
                "region": "us-west-2",
                "priority": 20,
                "weight": 80,
            },
        ],
        "capabilities": {
            "protocols": ["http-rest", "fhir-r4"],
            "fhir_r4": True,
        },
        "policy_tags": {
            "residency": ["US"],
            "prohibited_regions": ["CN", "RU"],
            "phi_allowed": True,
        },
    },
    # DE pathology agent — nexus-a2a-jsonrpc only
    {
        "agent_id": "gharra://de/agents/pathology-e2e",
        "display_name": "Pathology Analyzer",
        "jurisdiction": "DE",
        "endpoints": [
            {
                "url": "http://nexus-gateway:8100/rpc/pharmacy",
                "protocol": "nexus-a2a-jsonrpc",
                "region": "eu-central-1",
                "priority": 10,
                "weight": 100,
            }
        ],
        "capabilities": {
            "protocols": ["nexus-a2a-jsonrpc"],
            "fhir_r4": False,
            "stream_resume": True,
        },
        "policy_tags": {
            "residency": ["EU", "DE"],
            "phi_allowed": False,
        },
    },
    # IN diagnostics agent — non-GDPR-adequate jurisdiction (for policy testing)
    {
        "agent_id": "gharra://in/agents/diagnostics-e2e",
        "display_name": "India Diagnostics Agent",
        "jurisdiction": "IN",
        "endpoints": [
            {
                "url": "http://nexus-gateway:8100/rpc/triage",
                "protocol": "http-rest",
                "region": "ap-south-1",
                "priority": 10,
                "weight": 100,
            }
        ],
        "capabilities": {
            "protocols": ["http-rest"],
            "fhir_r4": True,
        },
        "policy_tags": {
            "residency": ["IN"],
            "phi_allowed": True,
            "data_classification": "restricted",
            "purpose_of_use": ["treatment", "research"],
        },
    },
    # JP telemedicine agent — GDPR-adequate jurisdiction (Japan has adequacy decision)
    {
        "agent_id": "gharra://jp/agents/telemedicine-e2e",
        "display_name": "Japan Telemedicine Agent",
        "jurisdiction": "JP",
        "endpoints": [
            {
                "url": "http://nexus-gateway:8100/rpc/triage",
                "protocol": "http-rest",
                "region": "ap-northeast-1",
                "priority": 10,
                "weight": 100,
            }
        ],
        "capabilities": {
            "protocols": ["http-rest"],
            "fhir_r4": True,
        },
        "policy_tags": {
            "residency": ["JP"],
            "phi_allowed": True,
            "data_classification": "confidential",
            "purpose_of_use": ["treatment"],
        },
    },
    # IE consent-required agent — requires consent proof and purpose declaration
    {
        "agent_id": "gharra://ie/agents/consent-gate-e2e",
        "display_name": "Consent Gate Agent",
        "jurisdiction": "IE",
        "endpoints": [
            {
                "url": "http://nexus-gateway:8100/rpc/triage",
                "protocol": "nexus-a2a-jsonrpc",
                "region": "eu-west-1",
                "priority": 10,
                "weight": 100,
            }
        ],
        "capabilities": {
            "protocols": ["nexus-a2a-jsonrpc"],
            "fhir_r4": True,
        },
        "trust": {
            "jwks_uri": "https://consent-gate.ie/.well-known/jwks.json",
            "token_binding": "dpop",
            "cert_thumbprints": ["sha256:consent001"],
        },
        "policy_tags": {
            "residency": ["EU", "IE"],
            "phi_allowed": True,
            "data_classification": "restricted",
            "consent_required": True,
            "purpose_of_use": ["treatment"],
        },
    },
]


# ── Jurisdiction-specific agents for sovereign registries ──────────────────

GB_AGENTS = [
    {
        "agent_id": "gharra://gb/agents/nhs-triage-e2e",
        "display_name": "NHS Triage Agent",
        "jurisdiction": "GB",
        "did_uri": "did:web:gharra.health:gb:agents:nhs-triage-e2e",
        "organisation_lei": "213800WSGIIZCXF1P572",
        "endpoints": [
            {
                "url": "http://nexus-gateway:8100/rpc/triage",
                "protocol": "nexus-a2a-jsonrpc",
                "region": "eu-west-2",
                "priority": 10,
                "weight": 100,
            },
        ],
        "capabilities": {
            "protocols": ["nexus-a2a-jsonrpc", "fhir-r4"],
            "fhir_r4": True,
            "stream_resume": True,
        },
        "trust": {
            "jwks_uri": "https://nhs-triage.gb/.well-known/jwks.json",
            "mtls_required": True,
            "token_binding": "dpop",
            "cert_thumbprints": ["sha256:nhs-triage-001"],
        },
        "policy_tags": {
            "residency": ["GB", "EU"],
            "phi_allowed": True,
            "data_classification": "restricted",
            "purpose_of_use": ["treatment"],
        },
    },
    {
        "agent_id": "gharra://gb/agents/nhs-discharge-e2e",
        "display_name": "NHS Discharge Agent",
        "jurisdiction": "GB",
        "endpoints": [
            {
                "url": "http://nexus-gateway:8100/rpc/diagnosis",
                "protocol": "http-rest",
                "region": "eu-west-2",
                "priority": 10,
                "weight": 100,
            },
        ],
        "capabilities": {
            "protocols": ["http-rest", "fhir-r4"],
            "fhir_r4": True,
        },
        "policy_tags": {
            "residency": ["GB"],
            "phi_allowed": True,
            "data_classification": "restricted",
            "purpose_of_use": ["treatment", "discharge"],
        },
    },
]

US_AGENTS = [
    {
        "agent_id": "gharra://us/agents/mayo-imaging-e2e",
        "display_name": "Mayo Imaging Agent",
        "jurisdiction": "US",
        "did_uri": "did:web:gharra.health:us:agents:mayo-imaging-e2e",
        "organisation_lei": "549300EX04Q2QBFQTQ27",
        "endpoints": [
            {
                "url": "http://nexus-gateway:8100/rpc/imaging",
                "protocol": "http-rest",
                "region": "us-east-1",
                "priority": 10,
                "weight": 100,
            },
        ],
        "capabilities": {
            "protocols": ["http-rest", "fhir-r4"],
            "fhir_r4": True,
        },
        "policy_tags": {
            "residency": ["US"],
            "phi_allowed": True,
            "data_classification": "restricted",
            "purpose_of_use": ["treatment", "research"],
        },
    },
    {
        "agent_id": "gharra://us/agents/cdc-surveillance-e2e",
        "display_name": "CDC Surveillance Agent",
        "jurisdiction": "US",
        "endpoints": [
            {
                "url": "http://nexus-gateway:8100/rpc/triage",
                "protocol": "nexus-a2a-jsonrpc",
                "region": "us-east-1",
                "priority": 10,
                "weight": 100,
            },
        ],
        "capabilities": {
            "protocols": ["nexus-a2a-jsonrpc"],
            "fhir_r4": False,
            "stream_resume": True,
        },
        "policy_tags": {
            "residency": ["US"],
            "phi_allowed": False,
            "data_classification": "confidential",
            "purpose_of_use": ["public_health"],
        },
    },
]


def _add_trust_anchors(body: dict) -> dict:
    """Add trust_anchors field to registry bodies (required by GHARRA API)."""
    base = body.get("api_base_url", "https://test.io")
    body.setdefault(
        "trust_anchors",
        [
            {
                "key_id": f"key-{uuid.uuid4().hex[:8]}",
                "alg": "ES256",
                "jwks_uri": f"{base}/.well-known/jwks.json",
                "thumbprint_sha256": f"sha256:{uuid.uuid4().hex[:16]}",
                "not_before": "2025-01-01T00:00:00Z",
                "not_after": "2027-01-01T00:00:00Z",
            }
        ],
    )
    return body


def seed_gharra(base_url: str | None = None) -> dict[str, str]:
    """Register canonical registries and agents. Returns ID map."""
    base = (base_url or GHARRA_BASE_URL).rstrip("/")
    ids: dict[str, str] = {}

    with httpx.Client(base_url=base, timeout=15.0) as client:
        # ── Registries ──
        for reg in REGISTRIES:
            body = _add_trust_anchors(dict(reg))
            resp = client.post(
                "/v1/registries",
                json=body,
                headers={"X-Idempotency-Key": _idem()},
            )
            if resp.status_code in (201, 200, 409):
                data = resp.json()
                key = f"{reg['display_name'].lower().replace(' ', '_')}_id"
                ids[key] = data.get("registry_id", "")
                logger.info("Registry %-22s → %s", reg["display_name"], ids[key])
            else:
                logger.warning(
                    "Registry %s failed: %d %s",
                    reg["display_name"],
                    resp.status_code,
                    resp.text[:200],
                )

        # ── Agents ──
        for agent in AGENTS:
            resp = client.post(
                "/v1/agents",
                json=agent,
                headers={"X-Idempotency-Key": _idem()},
            )
            if resp.status_code in (201, 200, 409):
                data = resp.json()
                agent_id = data.get("agent_id", agent.get("agent_id", ""))
                ids[agent["display_name"]] = agent_id
                logger.info(
                    "Agent    %-22s → %s  (status=%d)",
                    agent["display_name"],
                    agent_id,
                    resp.status_code,
                )
            else:
                logger.warning(
                    "Agent %s failed: %d %s",
                    agent["display_name"],
                    resp.status_code,
                    resp.text[:200],
                )

    logger.info("Seed complete (root) — %d entities registered", len(ids))
    return ids


def _seed_agents_to(base_url: str, agents: list[dict], label: str) -> dict[str, str]:
    """Seed a list of agents to a specific GHARRA instance."""
    base = base_url.rstrip("/")
    ids: dict[str, str] = {}

    with httpx.Client(base_url=base, timeout=15.0) as client:
        for agent in agents:
            resp = client.post(
                "/v1/agents",
                json=agent,
                headers={"X-Idempotency-Key": _idem()},
            )
            if resp.status_code in (201, 200, 409):
                data = resp.json()
                agent_id = data.get("agent_id", agent.get("agent_id", ""))
                ids[agent["display_name"]] = agent_id
                logger.info(
                    "[%s] Agent %-22s → %s  (status=%d)",
                    label, agent["display_name"], agent_id, resp.status_code,
                )
            else:
                logger.warning(
                    "[%s] Agent %s failed: %d %s",
                    label, agent["display_name"], resp.status_code, resp.text[:200],
                )

    logger.info("Seed complete (%s) — %d agents registered", label, len(ids))
    return ids


def seed_sovereign_gb(base_url: str | None = None) -> dict[str, str]:
    """Seed GB-specific agents to the GB sovereign registry."""
    return _seed_agents_to(base_url or GHARRA_GB_BASE_URL, GB_AGENTS, "GB")


def seed_sovereign_us(base_url: str | None = None) -> dict[str, str]:
    """Seed US-specific agents to the US sovereign registry."""
    return _seed_agents_to(base_url or GHARRA_US_BASE_URL, US_AGENTS, "US")


def seed_all(
    root_url: str | None = None,
    gb_url: str | None = None,
    us_url: str | None = None,
) -> dict[str, str]:
    """Seed all GHARRA instances (root + sovereigns). Returns combined ID map."""
    ids: dict[str, str] = {}
    ids.update(seed_gharra(root_url))
    ids.update(seed_sovereign_gb(gb_url))
    ids.update(seed_sovereign_us(us_url))
    logger.info("Seed all complete — %d total entities", len(ids))
    return ids


if __name__ == "__main__":
    ids = seed_all()
    if not ids:
        logger.error("Seeding failed — no entities registered")
        sys.exit(1)
    logger.info("Seeded IDs: %s", ids)
