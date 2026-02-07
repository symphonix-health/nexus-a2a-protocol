import os
import sys
import csv
import importlib


def import_from(src_dir: str, module: str):
    sys.path.insert(0, os.path.abspath(src_dir))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.pop(0)


def test_parse_csv_basic(tmp_path):
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "csv_read")

    p = tmp_path / "simple.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["a", "b"])  # header
        w.writerow(["1", "2"])  # row 1
        w.writerow(["3", "4"])  # row 2

    out = m.parse_csv(str(p))
    assert out == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]


def test_parse_csv_quoted_commas(tmp_path):
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "csv_read")

    p = tmp_path / "quoted.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "note"])  # header
        w.writerow(["Alice", "hello, world"])  # quoted comma
        w.writerow(["Bob", "x,y,z"])         # quoted comma

    out = m.parse_csv(str(p))
    assert out == [
        {"name": "Alice", "note": "hello, world"},
        {"name": "Bob", "note": "x,y,z"},
    ]
