"""Layer 1 — Pathway repository.

Loads, caches, and queries structured pathway definitions from the
file-system knowledge repository.  Includes governance currency
checking so the system can flag pathways that are overdue for
review or have superseded source guidelines.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Sequence

from .models import PathwayDefinition, PathwayStatus

logger = logging.getLogger(__name__)

_DEFAULT_DATA_ROOT = Path(__file__).parent


class PathwayRepository:
    """Read-only store of nationally approved pathway definitions."""

    def __init__(self, data_root: Path | None = None) -> None:
        self._root = data_root or _DEFAULT_DATA_ROOT
        self._cache: dict[str, PathwayDefinition] = {}

    # ── loading ──────────────────────────────────────────────────

    def load_all(self) -> int:
        """Recursively scan *data_root* for ``*.json`` pathway files and cache them."""
        count = 0
        for path in self._root.rglob("*.json"):
            if path.parent.name in {"tests", "__pycache__"}:
                continue
            try:
                defn = self._load_file(path)
                if defn is not None:
                    self._cache[defn.pathway_id] = defn
                    count += 1
            except Exception:
                logger.warning("Skipping invalid pathway file %s", path, exc_info=True)
        logger.info("Loaded %d pathway definitions from %s", count, self._root)
        return count

    def _load_file(self, path: Path) -> PathwayDefinition | None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if "pathway_id" not in raw:
            return None
        return PathwayDefinition.model_validate(raw)

    # ── queries ──────────────────────────────────────────────────

    def get(self, pathway_id: str) -> PathwayDefinition | None:
        return self._cache.get(pathway_id)

    def list_active(self, *, country: str | None = None) -> Sequence[PathwayDefinition]:
        results = [p for p in self._cache.values() if p.status == PathwayStatus.ACTIVE]
        if country:
            results = [p for p in results if p.country.upper() == country.upper()]
        return results

    def list_by_authority(self, authority: str) -> Sequence[PathwayDefinition]:
        return [
            p
            for p in self._cache.values()
            if p.source_authority.lower() == authority.lower()
        ]

    def search(self, query: str) -> Sequence[PathwayDefinition]:
        q = query.lower()
        return [
            p
            for p in self._cache.values()
            if q in p.title.lower() or q in p.description.lower() or q in p.pathway_id.lower()
        ]

    def list_needing_review(self, as_of: date | None = None) -> Sequence[PathwayDefinition]:
        """Return pathways that are overdue for clinical review."""
        return [p for p in self._cache.values() if p.governance.is_due_for_review(as_of)]

    def list_with_superseded_sources(self) -> Sequence[PathwayDefinition]:
        """Return pathways where at least one source guideline has been superseded."""
        return [p for p in self._cache.values() if p.governance.has_superseded_source()]

    def governance_report(self, as_of: date | None = None) -> list[dict]:
        """Generate a governance currency report for all loaded pathways.

        Returns a list of dicts with pathway_id, status, concerns, and
        source summary — suitable for dashboard display or audit export.
        """
        report = []
        for p in self._cache.values():
            concerns = p.needs_attention(as_of)
            report.append({
                "pathway_id": p.pathway_id,
                "title": p.title,
                "version": p.version,
                "status": p.status.value,
                "is_current": p.is_current(as_of),
                "clinical_owner": p.governance.clinical_owner,
                "last_reviewed": str(p.governance.last_reviewed_date) if p.governance.last_reviewed_date else None,
                "next_review": str(p.governance.next_review_date) if p.governance.next_review_date else None,
                "source_count": len(p.governance.sources),
                "highest_authority": p.governance.highest_authority().value if p.governance.highest_authority() else None,
                "concerns": concerns,
                "needs_attention": len(concerns) > 0,
            })
        return report

    @property
    def count(self) -> int:
        return len(self._cache)

    def all_ids(self) -> list[str]:
        return list(self._cache.keys())
