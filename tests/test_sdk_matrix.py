from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
# Prefer the in-repo copy; fall back to the optional nexus-a2a sub-repo.
_CANDIDATES = [
    _REPO_ROOT / "HelixCare" / "artefacts" / "matrices" / "nexus_sdk_transport_matrix.json",
    _REPO_ROOT / "nexus-a2a" / "artefacts" / "matrices" / "nexus_sdk_transport_matrix.json",
]
MATRIX = next((p for p in _CANDIDATES if p.exists()), _CANDIDATES[0])

_skip = not MATRIX.exists()
_reason = f"SDK matrix not found: {MATRIX}"


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
