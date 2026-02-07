"""CSV → JSON Lines converter using csv.DictReader and json.dumps."""

import csv
import json


def csv_to_jsonl(in_path: str, out_path: str) -> int:
    count = 0
    with open(in_path, "r", encoding="utf-8", newline="") as fin, open(
        out_path, "w", encoding="utf-8"
    ) as fout:
        reader = csv.DictReader(fin)
        for row in reader:
            fout.write(json.dumps(dict(row), ensure_ascii=False, separators=(",", ":")))
            fout.write("\n")
            count += 1
    return count
