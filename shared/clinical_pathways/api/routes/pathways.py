"""Pathway definition endpoints — read-only access to the knowledge repository."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...repository import PathwayRepository

router = APIRouter(prefix="/v1/pathways", tags=["pathways"])

# Injected at app startup
_repo: PathwayRepository | None = None


def set_repository(repo: PathwayRepository) -> None:
    global _repo
    _repo = repo


def _get_repo() -> PathwayRepository:
    if _repo is None:
        raise HTTPException(503, "Pathway repository not initialised")
    return _repo


@router.get("")
async def list_pathways(country: str | None = None):
    repo = _get_repo()
    pathways = repo.list_active(country=country)
    return {
        "count": len(pathways),
        "pathways": [
            {
                "pathway_id": p.pathway_id,
                "title": p.title,
                "version": p.version,
                "source_authority": p.source_authority,
                "country": p.country,
                "status": p.status.value,
            }
            for p in pathways
        ],
    }


@router.get("/{pathway_id}")
async def get_pathway(pathway_id: str):
    repo = _get_repo()
    pathway = repo.get(pathway_id)
    if pathway is None:
        raise HTTPException(404, f"Pathway '{pathway_id}' not found")
    return pathway.model_dump()


@router.get("/search/{query}")
async def search_pathways(query: str):
    repo = _get_repo()
    results = repo.search(query)
    return {
        "query": query,
        "count": len(results),
        "results": [
            {
                "pathway_id": p.pathway_id,
                "title": p.title,
                "source_authority": p.source_authority,
            }
            for p in results
        ],
    }
