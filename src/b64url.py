"""Base64url without padding (RFC 7515/7519 style)."""

import base64


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(s: str) -> bytes:
    pad_len = (-len(s)) % 4
    return base64.urlsafe_b64decode(s + ("=" * pad_len))
