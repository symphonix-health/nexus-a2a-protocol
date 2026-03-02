"""Profile registry agent stub for hybrid-profiles architecture."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from shared.nexus_common.generic_demo_agent import build_generic_demo_app

APP_DIR = str(Path(__file__).resolve().parent.parent)
app: FastAPI = build_generic_demo_app(
    default_name="Profile Registry Agent",
    app_dir=APP_DIR,
)
)
