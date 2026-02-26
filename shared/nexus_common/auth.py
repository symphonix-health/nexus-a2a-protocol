"""JWT authentication helpers for NEXUS-A2A protocol.

Includes:
  - mint_jwt()         — HS256 JWT for service-to-service calls
  - mint_persona_jwt() — HS256 JWT enriched with persona RBAC claims
  - verify_jwt()       — HS256 verification
  - verify_jwt_rs256() — RS256 OIDC verification (optional)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional
import threading

_jwks_cache_lock = threading.Lock()
CacheMap = dict[str, tuple[float, dict[str, Any]]]
_jwks_cache: CacheMap = {}
_oidc_cache: CacheMap = {}


class AuthError(Exception):
    """Raised when JWT authentication fails."""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode((data + pad).encode("utf-8"))


def mint_jwt(
    subject: str,
    secret: str,
    ttl_seconds: int = 3600,
    scope: str = "nexus:invoke",
) -> str:
    """Mint an HS256 JWT token."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + ttl_seconds,
        "scope": scope,
    }
    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    h = _b64url_encode(header_bytes)
    p = _b64url_encode(payload_bytes)
    signing_input = f"{h}.{p}".encode("utf-8")
    sig = hmac.new(
        secret.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    s = _b64url_encode(sig)
    return f"{h}.{p}.{s}"


def mint_persona_jwt(
    subject: str,
    secret: str,
    *,
    persona_id: str | None = None,
    agent_id: str | None = None,
    ttl_seconds: int = 3600,
    scope: str = "nexus:invoke",
) -> str:
    """Mint an HS256 JWT enriched with persona RBAC claims.

    When *persona_id* is supplied the token includes the following extra claims
    (sourced from ``config/personas.json`` via the PersonaRegistry):

    * ``persona_id``     — e.g. ``"P004"``
    * ``persona_name``   — e.g. ``"Triage Nurse"``
    * ``bulletrain_role``— e.g. ``"clinician_service"``
    * ``rbac_level``     — ``"High"`` / ``"Medium"`` / ``"Restricted"``
    * ``scopes``         — list of FHIR scopes (``["patient.read", ...]``)
    * ``purpose_of_use`` — ``"Treatment"`` / ``"Payment"`` / …
    * ``data_sensitivity``— ``"High"`` / ``"Medium"`` / ``"Low"``

    When *agent_id* is supplied it is embedded as the ``agent_id`` claim.

    Persona look-up is best-effort: if ``config/personas.json`` cannot be read
    the function still returns a valid (but scope-free) JWT.
    """
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + ttl_seconds,
        "scope": scope,
    }
    if agent_id:
        payload["agent_id"] = agent_id

    if persona_id:
        try:
            # Lazy import avoids a hard dependency cycle at module level.
            from shared.nexus_common.identity.persona_registry import (  # noqa: PLC0415
                get_persona_registry,
            )

            registry = get_persona_registry()
            persona = registry.get(persona_id)
            if persona:
                payload.update(persona.to_jwt_claims_dict())
        except Exception:  # noqa: BLE001
            pass  # Persona lookup is best-effort; never break token minting.

    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    h = _b64url_encode(header_bytes)
    p = _b64url_encode(payload_bytes)
    signing_input = f"{h}.{p}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    s = _b64url_encode(sig)
    return f"{h}.{p}.{s}"


def verify_jwt(
    token: str,
    secret: str,
    required_scope: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify an HS256 JWT token and return the decoded payload."""
    try:
        h_b64, p_b64, s_b64 = token.split(".")
    except ValueError as e:
        raise AuthError("Malformed JWT") from e
    signing_input = f"{h_b64}.{p_b64}".encode("utf-8")
    expected = hmac.new(
        secret.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    got = _b64url_decode(s_b64)
    if not hmac.compare_digest(expected, got):
        raise AuthError("Invalid signature")
    payload = json.loads(_b64url_decode(p_b64).decode("utf-8"))
    now = int(time.time())
    if int(payload.get("exp", 0)) < now:
        raise AuthError("Token expired")
    if required_scope:
        scope = payload.get("scope", "")
        if required_scope not in scope.split():
            raise AuthError("Insufficient scope")
    return payload


# ──────────────────────────────────────────────────────────────────────
# RS256 verification via OIDC discovery + JWKS (optional)
# Requires: PyJWT[crypto] and httpx. If unavailable, a helpful error is raised.
# ──────────────────────────────────────────────────────────────────────

class OidcError(AuthError):
    """Raised when OIDC-based verification cannot be performed."""


def _cache_get(cache: CacheMap, key: str, ttl: int) -> Optional[dict]:
    now = time.time()
    with _jwks_cache_lock:
        val = cache.get(key)
        if not val:
            return None
        ts, data = val
        if now - ts > ttl:
            cache.pop(key, None)
            return None
        return data


def _cache_set(cache: CacheMap, key: str, value: dict[str, Any]) -> None:
    with _jwks_cache_lock:
        cache[key] = (time.time(), value)


def _fetch_json(url: str) -> dict[str, Any]:
    try:
        import httpx  # type: ignore
    except Exception as e:  # pragma: no cover - optional path
        raise OidcError(
            "httpx is required for RS256 OIDC verification. "
            "Install with 'pip install .[security]'"
        ) from e
    resp = httpx.get(url, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def _get_oidc_configuration(
    discovery_url: str, ttl_seconds: int = 300
) -> dict[str, Any]:
    cached = _cache_get(_oidc_cache, discovery_url, ttl_seconds)
    if cached:
        return cached
    data = _fetch_json(discovery_url)
    if not isinstance(data, dict) or "jwks_uri" not in data:
        raise OidcError("Invalid OIDC discovery document – missing 'jwks_uri'")
    _cache_set(_oidc_cache, discovery_url, data)
    return data


def _get_jwks(jwks_uri: str, ttl_seconds: int = 300) -> dict[str, Any]:
    cached = _cache_get(_jwks_cache, jwks_uri, ttl_seconds)
    if cached:
        return cached
    data = _fetch_json(jwks_uri)
    if not isinstance(data, dict) or "keys" not in data:
        raise OidcError("Invalid JWKS – missing 'keys'")
    _cache_set(_jwks_cache, jwks_uri, data)
    return data


def verify_jwt_rs256(
    token: str,
    oidc_discovery_url: str,
    *,
    required_scope: Optional[str] = None,
    audience: Optional[str] = None,
    issuer: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify an RS256 JWT using an OIDC discovery URL + JWKS.

    This function requires optional dependencies: PyJWT[crypto] and httpx.
    Install with: pip install .[security]
    """
    try:
        import jwt  # type: ignore
        from jwt import PyJWKClient  # type: ignore
    except Exception as e:  # pragma: no cover - optional path
        raise OidcError(
            "PyJWT[crypto] is required for RS256 verification. "
            "Install with 'pip install .[security]'"
        ) from e

    # Discover JWKS URI
    cfg = _get_oidc_configuration(oidc_discovery_url)
    jwks_uri = cfg.get("jwks_uri")
    if not jwks_uri:
        raise OidcError("OIDC discovery missing 'jwks_uri'")

    # Optionally validate issuer from discovery
    expected_iss = issuer or cfg.get("issuer")

    # Prepare key fetcher (PyJWT caches internally; we also cache discovery)
    jwk_client = PyJWKClient(jwks_uri)
    try:
        signing_key = jwk_client.get_signing_key_from_jwt(token).key
    except Exception as e:
        raise AuthError(f"Unable to obtain signing key: {e}") from e

    options = {"verify_aud": audience is not None}
    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=audience,  # may be None
            issuer=expected_iss,  # may be None
            options=options,
        )
    except jwt.ExpiredSignatureError as e:  # type: ignore
        raise AuthError("Token expired") from e
    except jwt.InvalidTokenError as e:  # type: ignore
        raise AuthError(f"Invalid token: {e}") from e

    if required_scope:
        scope = payload.get("scope", "")
        if required_scope not in scope.split():
            raise AuthError("Insufficient scope")

    return payload
