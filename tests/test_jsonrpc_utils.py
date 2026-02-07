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


def test_build_and_validate_request():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "jsonrpc_utils")
    req = m.build_request("echo", {"x": 1}, 123)
    assert req["jsonrpc"] == "2.0"
    assert req["method"] == "echo"
    assert req["params"] == {"x": 1}
    assert req["id"] == 123
    # Validate should not raise
    m.validate_envelope(req)


def test_validate_rejects_invalid():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "jsonrpc_utils")
    with pytest.raises(ValueError):
        m.validate_envelope({"jsonrpc": "2.0", "method": 123})  # method must be str
    with pytest.raises(ValueError):
        m.validate_envelope({"jsonrpc": "1.0", "method": "x"})  # version
