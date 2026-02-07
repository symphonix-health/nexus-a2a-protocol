"""HMAC-SHA256 signing and constant-time verification."""

import hmac
import hashlib


def sign_message(payload: bytes, secret: bytes) -> str:
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def verify_message(payload: bytes, secret: bytes, signature_hex: str) -> bool:
    expected = sign_message(payload, secret)
    return hmac.compare_digest(expected, signature_hex)
