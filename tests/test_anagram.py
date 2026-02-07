import importlib
import os
import sys


def import_from(src_dir: str, module: str):
    sys.path.insert(0, os.path.abspath(src_dir))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.pop(0)


def test_is_anagram_true():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "anagram")
    assert m.is_anagram("listen", "silent") is True
    assert m.is_anagram("Dormitory", "Dirty room!!") is True


def test_is_anagram_false():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "anagram")
    assert m.is_anagram("hello", "world") is False
    assert m.is_anagram("aaab", "ab") is False
