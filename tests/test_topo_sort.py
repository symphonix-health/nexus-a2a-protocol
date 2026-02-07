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


def test_topo_sort_order():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "topo_sort")
    edges = {
        "A": ["B", "C"],
        "B": ["D"],
        "C": ["D"],
        "D": [],
    }
    order = m.topo_sort(edges)
    # Validate precedence constraints
    assert order.index("A") < order.index("B") < order.index("D")
    assert order.index("A") < order.index("C") < order.index("D")


def test_topo_sort_cycle():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "topo_sort")
    edges = {"X": ["Y"], "Y": ["X"]}
    with pytest.raises(ValueError):
        m.topo_sort(edges)
