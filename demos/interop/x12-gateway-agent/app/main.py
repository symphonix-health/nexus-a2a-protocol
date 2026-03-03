"""X12 gateway adapter stub for hybrid-profiles architecture."""

from pathlib import Path

from fastapi import FastAPI

from shared.nexus_common.generic_demo_agent import build_generic_demo_app

APP_DIR = str(Path(__file__).resolve().parent.parent)
app: FastAPI = build_generic_demo_app(
    default_name="X12 Gateway Agent",
    app_dir=APP_DIR,
)
