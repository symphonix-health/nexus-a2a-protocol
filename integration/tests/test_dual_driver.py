"""Dual-driver architecture regression tests.

Validates the Claude computer-use and Bevan scripted driver implementations,
the extended driver strategy enum, configuration fields, and contract
preservation with BrowserTaskResult.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

# Add BulletTrain to the Python path for direct imports
BT_ROOT = Path.home() / "bt" / "BulletTrain"
if str(BT_ROOT) not in sys.path:
    sys.path.insert(0, str(BT_ROOT))


# ---------------------------------------------------------------------------
# Phase 1: Driver strategy enum and catalog
# ---------------------------------------------------------------------------


class TestDriverStrategyEnum:
    """Validate that the extended SignalBoxDriver enum and DRIVER_CATALOG
    contain all six driver types with correct metadata."""

    def test_enum_has_six_values(self) -> None:
        from services.signalbox.driver_strategy import SignalBoxDriver

        values = [d.value for d in SignalBoxDriver]
        assert len(values) == 6
        assert "playwright" in values
        assert "selenium" in values
        assert "puppeteer" in values
        assert "desktop" in values
        assert "claude_computer_use" in values
        assert "bevan_scripted" in values

    def test_catalog_has_six_entries(self) -> None:
        from services.signalbox.driver_strategy import DRIVER_CATALOG, SignalBoxDriver

        assert len(DRIVER_CATALOG) == 6
        assert SignalBoxDriver.CLAUDE_COMPUTER_USE in DRIVER_CATALOG
        assert SignalBoxDriver.BEVAN_SCRIPTED in DRIVER_CATALOG

    def test_claude_catalog_entry_is_ga(self) -> None:
        from services.signalbox.driver_strategy import (
            DRIVER_CATALOG,
            SignalBoxDriver,
            SignalBoxSupportTier,
        )

        entry = DRIVER_CATALOG[SignalBoxDriver.CLAUDE_COMPUTER_USE]
        assert entry.support_tier == SignalBoxSupportTier.GA
        assert entry.implemented_in_repo is True
        assert entry.production_ui_supported is True
        assert entry.requires_browser is True

    def test_bevan_catalog_entry_is_ga(self) -> None:
        from services.signalbox.driver_strategy import (
            DRIVER_CATALOG,
            SignalBoxDriver,
            SignalBoxSupportTier,
        )

        entry = DRIVER_CATALOG[SignalBoxDriver.BEVAN_SCRIPTED]
        assert entry.support_tier == SignalBoxSupportTier.GA
        assert entry.implemented_in_repo is True
        assert entry.production_ui_supported is True
        assert entry.requires_browser is True

    def test_claude_strategy_validates(self) -> None:
        from services.signalbox.driver_strategy import (
            SignalBoxDriver,
            SignalBoxDriverStrategy,
            SignalBoxTaskMode,
        )

        strategy = SignalBoxDriverStrategy(
            driver=SignalBoxDriver.CLAUDE_COMPUTER_USE,
            task_mode=SignalBoxTaskMode.UI,
            headless=True,
        )
        assert strategy.driver == SignalBoxDriver.CLAUDE_COMPUTER_USE
        assert strategy.requires_browser() is True

    def test_bevan_strategy_validates(self) -> None:
        from services.signalbox.driver_strategy import (
            SignalBoxDriver,
            SignalBoxDriverStrategy,
            SignalBoxTaskMode,
        )

        strategy = SignalBoxDriverStrategy(
            driver=SignalBoxDriver.BEVAN_SCRIPTED,
            task_mode=SignalBoxTaskMode.UI,
            headless=True,
        )
        assert strategy.driver == SignalBoxDriver.BEVAN_SCRIPTED
        assert strategy.requires_browser() is True

    def test_runtime_guardrails_include_new_drivers(self) -> None:
        from services.signalbox.driver_strategy import (
            SignalBoxDriver,
            SignalBoxDriverStrategy,
        )

        claude_strat = SignalBoxDriverStrategy(driver=SignalBoxDriver.CLAUDE_COMPUTER_USE)
        guardrails = claude_strat.runtime_guardrails()
        assert "driver=claude_computer_use" in guardrails

        bevan_strat = SignalBoxDriverStrategy(driver=SignalBoxDriver.BEVAN_SCRIPTED)
        guardrails = bevan_strat.runtime_guardrails()
        assert "driver=bevan_scripted" in guardrails

    def test_invalid_driver_value_rejected(self) -> None:
        from services.signalbox.driver_strategy import SignalBoxDriverStrategy

        with pytest.raises(Exception):
            SignalBoxDriverStrategy(driver="nonexistent_driver")


# ---------------------------------------------------------------------------
# Phase 2: Configuration
# ---------------------------------------------------------------------------


class TestConfiguration:
    """Validate BrowserRuntimeConfig includes Claude and Bevan fields."""

    def test_config_has_claude_fields(self) -> None:
        from services.signalbox.state import BrowserRuntimeConfig

        import dataclasses

        field_names = [f.name for f in dataclasses.fields(BrowserRuntimeConfig)]
        assert "claude_api_key" in field_names
        assert "claude_model" in field_names
        assert "claude_max_turns" in field_names

    def test_config_has_bevan_fields(self) -> None:
        from services.signalbox.state import BrowserRuntimeConfig

        import dataclasses

        field_names = [f.name for f in dataclasses.fields(BrowserRuntimeConfig)]
        assert "bevan_endpoint" in field_names

    def test_config_defaults(self) -> None:
        from services.signalbox.state import get_env_config

        config = get_env_config()
        assert config.claude_model == "claude-sonnet-4-20250514"
        assert config.claude_max_turns == 20
        assert isinstance(config.bevan_endpoint, str)


# ---------------------------------------------------------------------------
# Phase 3: Computer-use executor
# ---------------------------------------------------------------------------


class TestPlaywrightBrowserExecutor:
    """Validate the PlaywrightBrowserExecutor implementation."""

    def test_executor_constructor(self) -> None:
        from bullettrain.gharra.computer_use import PlaywrightBrowserExecutor

        executor = PlaywrightBrowserExecutor(width=1280, height=800, headless=True)
        assert executor.display_width == 1280
        assert executor.display_height == 800

    def test_executor_not_started_assertion(self) -> None:
        from bullettrain.gharra.computer_use import PlaywrightBrowserExecutor

        executor = PlaywrightBrowserExecutor()
        with pytest.raises(AssertionError, match="not started"):
            asyncio.get_event_loop().run_until_complete(executor.screenshot())

    @pytest.mark.asyncio
    async def test_executor_start_and_screenshot(self) -> None:
        from bullettrain.gharra.computer_use import PlaywrightBrowserExecutor

        executor = PlaywrightBrowserExecutor(width=800, height=600, headless=True)
        try:
            await executor.start()
            assert executor.page is not None

            ss = await executor.screenshot()
            assert ss.width == 800
            assert ss.height == 600
            assert ss.media_type == "image/png"
            assert len(ss.data) > 0  # base64 data present
        finally:
            await executor.close()

    @pytest.mark.asyncio
    async def test_executor_close_idempotent(self) -> None:
        from bullettrain.gharra.computer_use import PlaywrightBrowserExecutor

        executor = PlaywrightBrowserExecutor(headless=True)
        await executor.start()
        await executor.close()
        await executor.close()  # should not raise

    @pytest.mark.asyncio
    async def test_executor_navigate(self) -> None:
        from bullettrain.gharra.computer_use import PlaywrightBrowserExecutor

        executor = PlaywrightBrowserExecutor(headless=True)
        try:
            await executor.start()
            await executor.navigate("about:blank")
        finally:
            await executor.close()

    @pytest.mark.asyncio
    async def test_executor_click(self) -> None:
        from bullettrain.gharra.computer_use import PlaywrightBrowserExecutor

        executor = PlaywrightBrowserExecutor(headless=True)
        try:
            await executor.start()
            await executor.navigate("about:blank")
            await executor.click(100, 100)  # click on blank page -- should not raise
        finally:
            await executor.close()

    @pytest.mark.asyncio
    async def test_executor_type_text(self) -> None:
        from bullettrain.gharra.computer_use import PlaywrightBrowserExecutor

        executor = PlaywrightBrowserExecutor(headless=True)
        try:
            await executor.start()
            await executor.navigate("about:blank")
            await executor.type_text("hello")  # type on blank page
        finally:
            await executor.close()

    @pytest.mark.asyncio
    async def test_executor_key(self) -> None:
        from bullettrain.gharra.computer_use import PlaywrightBrowserExecutor

        executor = PlaywrightBrowserExecutor(headless=True)
        try:
            await executor.start()
            await executor.navigate("about:blank")
            await executor.key("Enter")
        finally:
            await executor.close()

    @pytest.mark.asyncio
    async def test_executor_scroll(self) -> None:
        from bullettrain.gharra.computer_use import PlaywrightBrowserExecutor

        executor = PlaywrightBrowserExecutor(headless=True)
        try:
            await executor.start()
            await executor.navigate("about:blank")
            await executor.scroll(400, 300, "down", 3)
        finally:
            await executor.close()


# ---------------------------------------------------------------------------
# Phase 4: ComputerUseSession
# ---------------------------------------------------------------------------


class TestComputerUseSession:
    """Validate the ComputerUseSession constructor and result types."""

    def test_session_constructor(self) -> None:
        from bullettrain.gharra.computer_use import (
            ComputerUseSession,
            PlaywrightBrowserExecutor,
        )

        executor = PlaywrightBrowserExecutor()
        session = ComputerUseSession(
            executor=executor,
            model="claude-sonnet-4-20250514",
            max_turns=10,
            system="Test system prompt",
        )
        assert session is not None

    def test_result_dataclass_fields(self) -> None:
        from bullettrain.gharra.computer_use import ComputerUseResult

        result = ComputerUseResult(
            task="test",
            completed=True,
            summary="Done",
            turns=3,
            screenshots_taken=2,
            session_id="abc",
        )
        assert result.task == "test"
        assert result.completed is True
        assert result.turns == 3
        assert result.error is None

    def test_screenshot_manifest_entry(self) -> None:
        from bullettrain.gharra.computer_use import ScreenshotManifestEntry

        entry = ScreenshotManifestEntry(
            turn=1, timestamp=1234567890.0,
            width=1280, height=800,
            data_b64="abc123",
        )
        assert entry.turn == 1
        assert entry.media_type == "image/png"


# ---------------------------------------------------------------------------
# Phase 5: Claude driver bridge
# ---------------------------------------------------------------------------


class TestClaudeDriver:
    """Validate the Claude driver bridge returns proper BrowserTaskResult."""

    @pytest.mark.asyncio
    async def test_claude_driver_no_api_key(self) -> None:
        """Without ANTHROPIC_API_KEY, the driver returns a clear error."""
        import os

        # Temporarily clear the key
        original = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            from services.signalbox.claude_driver import run_task_with_claude
            from services.signalbox.state import get_env_config

            config = get_env_config()
            result = await run_task_with_claude(
                task="test",
                config=config,
                persona="doctor",
                session_id="test-001",
            )
            assert result.outcome == "failed"
            assert "ANTHROPIC_API_KEY" in result.error
        finally:
            if original:
                os.environ["ANTHROPIC_API_KEY"] = original

    def test_claude_result_has_all_fields(self) -> None:
        """BrowserTaskResult from Claude driver has all required fields."""
        from services.signalbox.browser_runtime import BrowserTaskResult

        import dataclasses

        field_names = [f.name for f in dataclasses.fields(BrowserTaskResult)]
        required = ["outcome", "steps_taken", "final_url", "screenshot_b64",
                     "elapsed_seconds", "llm_actions", "error"]
        for name in required:
            assert name in field_names, f"Missing field: {name}"


# ---------------------------------------------------------------------------
# Phase 6: Scenario matrix validation
# ---------------------------------------------------------------------------


class TestScenarioMatrix:
    """Validate the dual-driver regression matrix structure."""

    @pytest.fixture
    def matrix(self) -> list[dict]:
        matrix_path = Path(__file__).resolve().parent.parent / "scenarios" / "dual_driver_regression_matrix.json"
        with open(matrix_path) as f:
            return json.load(f)

    def test_matrix_has_scenarios(self, matrix: list[dict]) -> None:
        assert len(matrix) >= 25

    def test_all_scenarios_have_14_columns(self, matrix: list[dict]) -> None:
        required_columns = {
            "use_case_id", "poc_demo", "scenario_title", "scenario_type",
            "requirement_ids", "preconditions", "input_payload", "transport",
            "auth_mode", "expected_http_status", "expected_result",
            "expected_events", "error_condition", "test_tags",
        }
        for scenario in matrix:
            missing = required_columns - set(scenario.keys())
            assert not missing, f"{scenario['use_case_id']} missing columns: {missing}"

    def test_scenario_type_distribution(self, matrix: list[dict]) -> None:
        types = [s["scenario_type"] for s in matrix]
        positive = types.count("positive")
        negative = types.count("negative")
        edge = types.count("edge")
        assert positive >= 20, f"Expected >= 20 positive, got {positive}"
        assert negative >= 2, f"Expected >= 2 negative, got {negative}"
        assert edge >= 1, f"Expected >= 1 edge, got {edge}"

    def test_unique_use_case_ids(self, matrix: list[dict]) -> None:
        ids = [s["use_case_id"] for s in matrix]
        assert len(ids) == len(set(ids)), "Duplicate use_case_ids found"

    def test_all_ids_start_with_ddr(self, matrix: list[dict]) -> None:
        for s in matrix:
            assert s["use_case_id"].startswith("DDR-"), f"Invalid ID prefix: {s['use_case_id']}"
