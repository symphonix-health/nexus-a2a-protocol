import os
import sys
import importlib
import hashlib


def import_from(src_dir: str, module: str):
    sys.path.insert(0, os.path.abspath(src_dir))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.pop(0)


def reference_merkle(chunks: list[bytes]) -> str:
    if not chunks:
        return hashlib.sha256(b"").hexdigest()
    level = [hashlib.sha256(c).digest() for c in chunks]
    while len(level) > 1:
        nxt = []
        it = iter(level)
        for a in it:
            try:
                b = next(it)
            except StopIteration:
                b = a
            nxt.append(hashlib.sha256(a + b).digest())
        level = nxt
    return level[0].hex()


def test_merkle_root_matches_reference():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "merkle")
    chunks = [b"a", b"b", b"c", b"d", b"e"]
    assert m.merkle_root(chunks) == reference_merkle(chunks)
    assert m.merkle_root([]) == reference_merkle([])
