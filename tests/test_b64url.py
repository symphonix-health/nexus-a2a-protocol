import os
import sys
import importlib


def import_from(src_dir: str, module: str):
    sys.path.insert(0, os.path.abspath(src_dir))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.pop(0)


def test_b64url_roundtrip_no_padding():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "b64url")
    data = b"\x00\x01\x02hello world!\xff"
    s = m.b64url_encode(data)
    assert "=" not in s
    out = m.b64url_decode(s)
    assert out == data
