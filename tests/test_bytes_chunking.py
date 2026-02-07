import os
import sys
import importlib


def import_from(src_dir: str, module: str):
    sys.path.insert(0, os.path.abspath(src_dir))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.pop(0)


def test_chunk_and_unchunk_roundtrip():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "bytes_chunking")
    data = b"abcdefghijklmnopqrstuvwxyz"
    chunks = m.chunk_bytes(data, 5)
    assert all(isinstance(c, (bytes, bytearray)) for c in chunks)
    assert chunks[0] == b"abcde" and chunks[-1] == b"z"
    out = m.unchunk_bytes(chunks)
    assert out == data
