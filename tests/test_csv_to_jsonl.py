import os
import sys
import csv
import json
import importlib


def import_from(src_dir: str, module: str):
    sys.path.insert(0, os.path.abspath(src_dir))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.pop(0)


def test_csv_to_jsonl_roundtrip(tmp_path):
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "csv_to_jsonl")

    csv_path = tmp_path / "in.csv"
    jsonl_path = tmp_path / "out.jsonl"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "note"])  # header
        w.writerow(["Alice", "hello, world"])  # quoted comma handled
        w.writerow(["Bob", "x,y,z"])         # quoted comma handled

    count = m.csv_to_jsonl(str(csv_path), str(jsonl_path))
    assert count == 2

    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    objs = [json.loads(line) for line in lines]
    assert objs == [
        {"name": "Alice", "note": "hello, world"},
        {"name": "Bob", "note": "x,y,z"},
    ]
