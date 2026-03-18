"""Convenience loader that returns a ready-to-use PathwayRepository."""

from __future__ import annotations

from pathlib import Path

from .repository import PathwayRepository

_DEFAULT_ROOT = Path(__file__).parent


def load_pathways(data_root: Path | None = None) -> PathwayRepository:
    """Load all pathway definitions and return a populated repository."""
    repo = PathwayRepository(data_root or _DEFAULT_ROOT)
    repo.load_all()
    return repo
