"""Deterministic JSON serialization with sorted keys and compact separators."""

import json


def canonical_dumps(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
