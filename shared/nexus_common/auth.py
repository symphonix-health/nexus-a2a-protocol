"""JWT authentication helpers for NEXUS-A2A protocol (HS256)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional


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
    payload = {"sub": subject, "iat": now, "exp": now + ttl_seconds, "scope": scope}
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
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
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
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
