from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
# Prefer the in-repo copy; fall back to the optional nexus-a2a sub-repo.
_CANDIDATES = [
    _REPO_ROOT / "HelixCare" / "artefacts" / "matrices" / "nexus_command_centre_load_matrix.json",
    _REPO_ROOT / "nexus-a2a" / "artefacts" / "matrices" / "nexus_command_centre_load_matrix.json",
]
MATRIX_PATH = next((p for p in _CANDIDATES if p.exists()), _CANDIDATES[0])
GATE_DIR = MATRIX_PATH.parent / "gates"

_skip = not MATRIX_PATH.exists()
_reason = f"Load matrix not found: {MATRIX_PATH}"


def _load_rows() -> list[dict]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


@pytest.mark.skipif(_skip, reason=_reason)
def test_load_matrix_is_expanded_for_hyperscale_backlog() -> None:
    rows = _load_rows()
    assert len(rows) >= 7000


@pytest.mark.skipif(_skip, reason=_reason)
def test_load_matrix_contains_high_concurrency_profiles() -> None:
    rows = _load_rows()
    counts: list[int] = []
    for row in rows:
        payload = row.get("input_payload", {})
        value = payload.get("concurrent_count")
        if isinstance(value, int):
            counts.append(value)
    assert counts
    assert max(counts) >= 2000


@pytest.mark.skipif(_skip, reason=_reason)
def test_load_matrix_has_gate_tags_for_milestones() -> None:
    rows = _load_rows()
    expected = {"gate:g0", "gate:g1", "gate:g2", "gate:g3", "gate:g4"}
    found: set[str] = set()
    for row in rows:
        tags = row.get("test_tags", [])
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, str) and tag in expected:
                    found.add(tag)
    assert expected.issubset(found)


@pytest.mark.skipif(_skip, reason=_reason)
def test_load_matrix_has_2m_target_gate_profile() -> None:
    rows = _load_rows()
    targets = []
    for row in rows:
        gate = row.get("load_gate", {})
        value = gate.get("target_concurrency")
        if isinstance(value, int):
            targets.append(value)
    assert targets
    assert max(targets) >= 2_000_000


@pytest.mark.skipif(_skip, reason=_reason)
def test_gate_matrix_artifacts_exist() -> None:
    expected = (
        GATE_DIR / "nexus_command_centre_load_matrix_gate_g0.json",
        GATE_DIR / "nexus_command_centre_load_matrix_gate_g1.json",
        GATE_DIR / "nexus_command_centre_load_matrix_gate_g2.json",
        GATE_DIR / "nexus_command_centre_load_matrix_gate_g3.json",
        GATE_DIR / "nexus_command_centre_load_matrix_gate_g4.json",
    )
    for path in expected:
        assert path.exists(), f"Missing gate matrix: {path}"
