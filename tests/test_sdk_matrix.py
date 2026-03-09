from __future__ import annotations

import json
from pathlib import Path


MATRIX = (
    Path(__file__).resolve().parents[1]
    / "nexus-a2a"
    / "artefacts"
    / "matrices"
    / "nexus_sdk_transport_matrix.json"
)



def test_sdk_transport_matrix_exists_with_baseline_size() -> None:
    rows = json.loads(MATRIX.read_text(encoding="utf-8"))
    assert isinstance(rows, list)
    assert len(rows) == 44



def test_sdk_transport_matrix_has_required_transport_coverage() -> None:
    rows = json.loads(MATRIX.read_text(encoding="utf-8"))
    transports = {row.get("transport") for row in rows if isinstance(row, dict)}
    assert {"simulation", "http_sse", "websocket", "legacy"}.issubset(transports)



def test_sdk_transport_matrix_contains_smoke_subset() -> None:
    rows = json.loads(MATRIX.read_text(encoding="utf-8"))
    smoke = [row for row in rows if isinstance(row, dict) and "smoke" in row.get("test_tags", [])]
    assert smoke
    assert len(smoke) < len(rows)
