import os
import sys
import importlib
import pytest


def import_from(src_dir: str, module: str):
    sys.path.insert(0, os.path.abspath(src_dir))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.pop(0)


def test_validate_simple_schema():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "json_validate")
    schema = {"types": {"a": "str", "b": "int", "c": "bool"}, "required": ["a", "b"]}
    m.validate_simple_schema({"a": "x", "b": 1, "c": False}, schema)
    # Missing required
    with pytest.raises(ValueError):
        m.validate_simple_schema({"a": "x"}, schema)
    # Wrong types
    with pytest.raises(ValueError):
        m.validate_simple_schema({"a": 1, "b": 2}, schema)
