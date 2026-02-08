#!/usr/bin/env python3
"""Mint a PoC HS256 JWT for NEXUS-A2A demos.

Usage:
  export NEXUS_JWT_SECRET="dev-secret-change-me"
  python tools/mint_jwt.py
"""

from __future__ import annotations

import os
import sys

# Allow running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.nexus_common.auth import mint_jwt  # noqa: E402

secret = os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me")
subject = os.getenv("NEXUS_JWT_SUBJECT", "demo-user")
scope = os.getenv("NEXUS_JWT_SCOPE", "nexus:invoke")
ttl = int(os.getenv("NEXUS_JWT_TTL_SECONDS", "86400"))

token = mint_jwt(subject, secret, ttl_seconds=ttl, scope=scope)
print(token)
