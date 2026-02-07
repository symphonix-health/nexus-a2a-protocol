import os
import sys
import importlib
import json


def import_from(src_dir: str, module: str):
    sys.path.insert(0, os.path.abspath(src_dir))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.pop(0)


def test_canonical_dumps_deterministic():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "canonical_json")
    obj1 = {"b": 2, "a": {"y": 2, "x": 1}}
    obj2 = {"a": {"x": 1, "y": 2}, "b": 2}
    s1 = m.canonical_dumps(obj1)
    s2 = m.canonical_dumps(obj2)
    assert s1 == s2
    # Validate it's valid JSON and has no spaces
    parsed = json.loads(s1)
    assert parsed == obj2
    assert " " not in s1 and "\n" not in s1
