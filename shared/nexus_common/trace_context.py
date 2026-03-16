"""W3C trace-context helpers for inter-agent request propagation.

Mitigation 5.2 -- Three-Layer Identifier Standard:
  Correlation IDs use RFC 9562 UUID v7 (timestamp-sortable) instead of
  random hex tokens. UUID v7 provides millisecond-precision temporal
  ordering while preserving uniqueness guarantees.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from typing import Mapping


def _uuid_v7_hex() -> str:
    """Generate an RFC 9562 UUID v7 as a 32-char hex string.

    Layout (128 bits):
      - bits  0-47: unix_ts_ms (48-bit millisecond timestamp)
      - bits 48-51: version (0b0111 = 7)
      - bits 52-63: rand_a (12 bits)
      - bits 64-65: variant (0b10)
      - bits 66-127: rand_b (62 bits)
    """
    ts_ms = int(time.time() * 1000) & 0xFFFF_FFFF_FFFF  # 48-bit ms
    rand_bytes = secrets.token_bytes(10)  # 80 random bits
    rand_a = (rand_bytes[0] << 4) | (rand_bytes[1] >> 4)  # 12 bits
    rand_b_bytes = bytearray(8)
    rand_b_bytes[0] = (rand_bytes[1] & 0x0F) << 4 | (rand_bytes[2] >> 4)
    rand_b_bytes[1] = (rand_bytes[2] & 0x0F) << 4 | (rand_bytes[3] >> 4)
    rand_b_bytes[2:8] = rand_bytes[4:10]

    # Pack: 6 bytes timestamp + 2 bytes (version|rand_a) + 8 bytes (variant|rand_b)
    hi = (ts_ms << 16) | (0x7000 | rand_a)  # 64-bit high word
    lo_raw = int.from_bytes(rand_b_bytes, "big")
    lo = (0b10 << 62) | (lo_raw & 0x3FFF_FFFF_FFFF_FFFF)  # set variant bits

    return f"{hi:016x}{lo:016x}"


def _normalize_hex(value: str, size: int) -> str:
    token = "".join(ch for ch in value.lower() if ch in "0123456789abcdef")
    if len(token) == size:
        return token
    if len(token) > size:
        return token[-size:]
    return token.rjust(size, "0")


def _derive_trace_hex(trace_id: str | None) -> str:
    raw = str(trace_id or "").strip()
    if raw:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return _normalize_hex(digest, 32)
    return _uuid_v7_hex()


def _derive_span_hex(trace_id: str | None) -> str:
    raw = str(trace_id or "").strip()
    if raw:
        digest = hashlib.sha256((raw + "::span").encode("utf-8")).hexdigest()
        return _normalize_hex(digest, 16)
    # Use lower 64 bits of a UUID v7 for span IDs (still temporally unique)
    return _uuid_v7_hex()[16:]


def build_traceparent(trace_id: str | None, *, sampled: bool = True) -> str:
    trace_hex = _derive_trace_hex(trace_id)
    span_hex = _derive_span_hex(trace_id)
    flags = "01" if sampled else "00"
    return f"00-{trace_hex}-{span_hex}-{flags}"


def extract_trace_context(headers: Mapping[str, str]) -> tuple[str | None, str | None]:
    traceparent = str(headers.get("traceparent", "")).strip() or None
    tracestate = str(headers.get("tracestate", "")).strip() or None
    return traceparent, tracestate


def inject_trace_context(
    headers: dict[str, str],
    *,
    trace_id: str | None,
    tracestate: str | None = None,
) -> tuple[str, str | None]:
    sampled = os.getenv("NEXUS_TRACE_SAMPLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    traceparent = build_traceparent(trace_id, sampled=sampled)
    headers["traceparent"] = traceparent
    if tracestate:
        headers["tracestate"] = tracestate
    return traceparent, tracestate
