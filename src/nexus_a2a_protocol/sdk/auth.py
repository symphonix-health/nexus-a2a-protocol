"""Authentication helpers for SDK transport clients."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

_DEFAULT_SECRET = "dev-secret-change-me"



def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")



def mint_jwt(
    subject: str,
    secret: str,
    ttl_seconds: int = 3600,
    scope: str = "nexus:invoke",
) -> str:
    """Mint a simple HS256 JWT without external crypto dependencies."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + int(ttl_seconds),
        "scope": scope,
    }
    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    h = _b64url_encode(header_bytes)
    p = _b64url_encode(payload_bytes)
    signing_input = f"{h}.{p}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    s = _b64url_encode(sig)
    return f"{h}.{p}.{s}"



def resolve_jwt_token(
    *,
    token_env: str = "NEXUS_JWT_TOKEN",
    secret_env: str = "NEXUS_JWT_SECRET",
    subject_env: str = "NEXUS_JWT_SUBJECT",
    scope_env: str = "NEXUS_JWT_SCOPE",
) -> str:
    """Resolve a bearer token from env or mint one from a configured secret."""
    existing = os.getenv(token_env, "").strip()
    if existing:
        return existing

    secret = os.getenv(secret_env, "").strip()
    if not secret:
        logger.warning(
            "%s not set; falling back to default dev secret. Set %s or %s for production use.",
            secret_env,
            secret_env,
            token_env,
        )
        secret = _DEFAULT_SECRET

    subject = os.getenv(subject_env, "sdk-client").strip() or "sdk-client"
    scope = os.getenv(scope_env, "nexus:invoke").strip() or "nexus:invoke"
    return mint_jwt(subject, secret, ttl_seconds=86400, scope=scope)
