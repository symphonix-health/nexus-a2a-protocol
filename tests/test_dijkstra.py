import os
import sys
import importlib


def import_from(src_dir: str, module: str):
    sys.path.insert(0, os.path.abspath(src_dir))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.pop(0)


def test_shortest_paths_basic():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "dijkstra")
    graph = {
        "A": [("B", 1), ("C", 4)],
        "B": [("C", 2), ("D", 5)],
        "C": [("D", 1)],
        "D": [],
    }
    dist = m.shortest_paths(graph, "A")
    assert dist == {"A": 0, "B": 1, "C": 3, "D": 4}
