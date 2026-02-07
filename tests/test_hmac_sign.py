import os
import sys
import importlib


def import_from(src_dir: str, module: str):
    sys.path.insert(0, os.path.abspath(src_dir))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.pop(0)


def test_hmac_sign_and_verify():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "hmac_sign")
    payload = b"hello world"
    secret = b"supersecret"
    sig = m.sign_message(payload, secret)
    assert isinstance(sig, str) and len(sig) == 64  # hex length
    assert m.verify_message(payload, secret, sig) is True
    assert m.verify_message(payload + b"!", secret, sig) is False
