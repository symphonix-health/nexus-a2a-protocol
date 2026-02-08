"""Feature-flagged DID verification stub for NEXUS-A2A vNext."""

from __future__ import annotations

import os


def did_verify_enabled() -> bool:
    """Check whether DID signature verification is enabled via env flag."""
    return os.getenv("DID_VERIFY", "false").lower() == "true"


def verify_did_signature(*args: object, **kwargs: object) -> bool:
    """Stub: always returns True. Replace with DIDKit / JWS when available."""
    return True
