"""Clinical Pathways API — FastAPI application.

Serves pathway definitions and the personalisation endpoint.
"""

from __future__ import annotations

from fastapi import FastAPI

from ..engine.audit import AuditLogger
from ..engine.personaliser import PathwayPersonaliser
from ..loader import load_pathways
from .routes import health, pathways, personalise

app = FastAPI(
    title="Clinical Pathways Personalisation Service",
    version="0.1.0",
    description=(
        "Personalises nationally approved clinical pathways using patient context. "
        "Implements the four-layer architecture: Standard Pathway → Patient Context → "
        "Decision → Governance."
    ),
)


@app.on_event("startup")
async def startup():
    repo = load_pathways()
    audit = AuditLogger()
    personaliser = PathwayPersonaliser(audit_logger=audit)

    pathways.set_repository(repo)
    personalise.set_dependencies(repo, personaliser)


app.include_router(health.router)
app.include_router(pathways.router)
app.include_router(personalise.router)
