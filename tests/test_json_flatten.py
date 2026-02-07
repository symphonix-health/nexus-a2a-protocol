import importlib
import os
import sys


def import_from(src_dir: str, module: str):
    sys.path.insert(0, os.path.abspath(src_dir))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.pop(0)


def test_flatten_basic():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "json_flatten")
    obj = {"a": {"b": 1, "c": {"d": 2}}, "e": 3}
    out = m.flatten_json(obj, ".")
    assert out == {"a.b": 1, "a.c.d": 2, "e": 3}


def test_flatten_with_list_and_sep():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "json_flatten")
    obj = {"a": [1, {"x": 2}], "b": {"y": [3, 4]}}
    out = m.flatten_json(obj, sep="/")
    assert out == {"a/0": 1, "a/1/x": 2, "b/y/0": 3, "b/y/1": 4}
