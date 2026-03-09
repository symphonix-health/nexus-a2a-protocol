"""Fixtures for SDK transport harness tests."""

from __future__ import annotations

import pathlib

import pytest
import pytest_asyncio

from tests.sdk_harness.runner import close_context, create_context, get_report


@pytest_asyncio.fixture(scope="session")
async def sdk_harness_context():
    context = await create_context()
    try:
        yield context
    finally:
        await close_context(context)


@pytest.fixture(scope="session", autouse=True)
def _save_sdk_report():
    yield
    report = get_report()
    out = pathlib.Path(__file__).resolve().parents[2] / "docs" / "sdk-conformance-report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    report.save(out)
