from __future__ import annotations

import json
from pathlib import Path

import pytest

MATRIX = (
    Path(__file__).resolve().parents[1]
    / "nexus-a2a"
    / "artefacts"
    / "matrices"
    / "nexus_sdk_transport_matrix.json"
)

_skip = not MATRIX.exists()
_reason = f"SDK matrix not found (requires nexus-a2a repo): {MATRIX}"


@pytest.mark.skipif(_skip, reason=_reason)
def test_sdk_transport_matrix_exists_with_baseline_size() -> None:
    rows = json.loads(MATRIX.read_text(encoding="utf-8"))
    assert isinstance(rows, list)
    assert len(rows) == 44



@pytest.mark.skipif(_skip, reason=_reason)
def test_sdk_transport_matrix_has_required_transport_coverage() -> None:
    rows = json.loads(MATRIX.read_text(encoding="utf-8"))
    transports = {row.get("transport") for row in rows if isinstance(row, dict)}
    assert {"simulation", "http_sse", "websocket", "legacy"}.issubset(transports)



@pytest.mark.skipif(_skip, reason=_reason)
def test_sdk_transport_matrix_contains_smoke_subset() -> None:
    rows = json.loads(MATRIX.read_text(encoding="utf-8"))
    smoke = [row for row in rows if isinstance(row, dict) and "smoke" in row.get("test_tags", [])]
    assert smoke
    assert len(smoke) < len(rows)
