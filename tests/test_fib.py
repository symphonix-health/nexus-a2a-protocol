import importlib
import os
import sys


def import_from(src_dir: str, module: str):
    sys.path.insert(0, os.path.abspath(src_dir))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.pop(0)


def test_fib_basic():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "fib")
    assert m.fib(0) == 0
    assert m.fib(1) == 1
    assert m.fib(2) == 1
    assert m.fib(3) == 2
    assert m.fib(10) == 55


def test_fib_large():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "fib")
    assert m.fib(30) == 832040
    assert m.fib(50) == 12586269025
