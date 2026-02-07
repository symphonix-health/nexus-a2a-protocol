"""CSV parsing: read a UTF-8 CSV with header and return row dicts."""

from typing import List, Dict
import csv


def parse_csv(path: str) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]
