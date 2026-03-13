"""Matrix-driven SDK transport conformance tests."""

from __future__ import annotations

import os
import time

import pytest

from tests.sdk_harness.runner import SdkScenarioResult, execute_scenario, get_report, pytest_ids, scenarios_for

MATRIX = "nexus_sdk_transport_matrix.json"
PROFILE = os.getenv("SDK_HARNESS_PROFILE", "full").strip().lower()
try:
    SCENARIOS = scenarios_for(MATRIX, profile=PROFILE)
except FileNotFoundError:
    SCENARIOS = []
    pytestmark = pytest.mark.skip(
        reason=f"SDK matrix {MATRIX} not found (requires nexus-a2a repo)"
    )


@pytest.mark.parametrize("scenario", SCENARIOS, ids=pytest_ids(SCENARIOS))
@pytest.mark.asyncio
async def test_sdk_transport_matrix(scenario: dict, sdk_harness_context) -> None:
    result = SdkScenarioResult(
        use_case_id=str(scenario.get("use_case_id") or "unknown"),
        scenario_title=str(scenario.get("scenario_title") or ""),
        scenario_type=str(scenario.get("scenario_type") or ""),
        transport=str(scenario.get("transport") or "simulation"),
    )

    t0 = time.monotonic()
    try:
        message = await execute_scenario(scenario, sdk_harness_context)
        result.status = "pass"
        result.message = message
    except AssertionError as exc:
        result.status = "fail"
        result.message = str(exc)
        raise
    except Exception as exc:  # noqa: BLE001
        result.status = "error"
        result.message = str(exc)
        raise
    finally:
        result.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(result)
