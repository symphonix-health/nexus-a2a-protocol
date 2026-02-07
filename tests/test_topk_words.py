import os
import sys
import importlib


def import_from(src_dir: str, module: str):
    sys.path.insert(0, os.path.abspath(src_dir))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.pop(0)


def test_top_k_words_basic():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "topk_words")
    text = "Hello, hello! world; World world?"
    assert m.top_k_words(text, 2) == [("world", 3), ("hello", 2)]


def test_top_k_words_tie_break():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "topk_words")
    text = "a b c a b c x"
    # counts: a=2, b=2, c=2, x=1 => top3 with ties by alpha -> a, b, c
    assert m.top_k_words(text, 3) == [("a", 2), ("b", 2), ("c", 2)]
