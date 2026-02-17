"""Unit tests for shared.nexus_common.mcp_adapter.

Tests cover registry loading, URL resolution, auth bootstrap,
SSE parsing, and NEXUS-to-MCP progress mapping.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure shared/ is importable
REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED_DIR = REPO_ROOT / "shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from nexus_common.mcp_adapter import (  # noqa: E402
    AgentInfo,
    SseEvent,
    load_agent_registry,
    map_nexus_event_to_progress,
    parse_sse_chunk,
    resolve_agent_url,
    resolve_jwt_token,
)

# ── Fixtures ──────────────────────────────────────────────────────────

CONFIG_PATH = str(REPO_ROOT / "config" / "agents.json")


@pytest.fixture()
def real_config_path():
    """Path to the real config/agents.json in the repo."""
    return CONFIG_PATH


@pytest.fixture()
def sample_registry() -> dict[str, AgentInfo]:
    """Minimal agent registry for testing."""
    return {
        "triage_agent": AgentInfo(
            alias="triage_agent",
            port=8021,
            url="http://localhost:8021",
            description="Patient triage agent",
            category="ed_triage",
        ),
        "diagnosis_agent": AgentInfo(
            alias="diagnosis_agent",
            port=8022,
            url="http://localhost:8022",
            description="AI-powered diagnosis agent",
            category="ed_triage",
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
# U1–U3: Registry loading
# ═══════════════════════════════════════════════════════════════════════


class TestLoadAgentRegistry:
    """Tests for load_agent_registry()."""

    def test_load_from_config_file(self, real_config_path: str):
        """U1: Parse config/agents.json into a flat dict with correct aliases."""
        registry = load_agent_registry(real_config_path)

        assert isinstance(registry, dict)
        assert len(registry) >= 20, f"Expected 20+ agents, got {len(registry)}"

        # Spot-check known agents
        assert "triage_agent" in registry
        assert registry["triage_agent"].port == 8021
        assert registry["triage_agent"].category == "ed_triage"

        assert "imaging_agent" in registry
        assert registry["imaging_agent"].port == 8024
        assert registry["imaging_agent"].category == "helixcare"

        assert "discharge_agent" in registry
        assert registry["discharge_agent"].port == 8027

    def test_load_from_env(self):
        """U2: AGENT_URLS env takes priority over config."""
        with patch.dict(os.environ, {"AGENT_URLS": "http://a:8021,http://b:8022"}):
            registry = load_agent_registry()

        assert len(registry) == 2
        aliases = list(registry.keys())
        assert "agent_8021" in aliases
        assert "agent_8022" in aliases
        assert registry["agent_8021"].url == "http://a:8021"
        assert registry["agent_8022"].url == "http://b:8022"

    def test_load_missing_config(self, tmp_path: Path):
        """U3: No env, no config file → returns empty dict, no crash."""
        with patch.dict(os.environ, {"AGENT_URLS": ""}, clear=False):
            registry = load_agent_registry(str(tmp_path / "nonexistent.json"))

        assert registry == {}


# ═══════════════════════════════════════════════════════════════════════
# U4–U6: URL resolution
# ═══════════════════════════════════════════════════════════════════════


class TestResolveAgentUrl:
    """Tests for resolve_agent_url()."""

    def test_resolve_by_alias(self, sample_registry: dict):
        """U4: Known alias resolves to correct URL."""
        url = resolve_agent_url("triage_agent", sample_registry)
        assert url == "http://localhost:8021"

    def test_resolve_raw_url(self, sample_registry: dict):
        """U5: A raw URL passes through unchanged."""
        url = resolve_agent_url("http://custom:9999", sample_registry)
        assert url == "http://custom:9999"

    def test_resolve_raw_url_strips_trailing_slash(self, sample_registry: dict):
        """U5b: Trailing slashes are stripped from raw URLs."""
        url = resolve_agent_url("http://custom:9999/", sample_registry)
        assert url == "http://custom:9999"

    def test_resolve_unknown_alias_raises(self, sample_registry: dict):
        """U6: Unknown alias raises ValueError with descriptive message."""
        with pytest.raises(ValueError, match="Unknown agent alias"):
            resolve_agent_url("nonexistent_agent", sample_registry)

    def test_resolve_unknown_alias_includes_available(self, sample_registry: dict):
        """U6b: Error message lists available aliases."""
        with pytest.raises(ValueError, match="triage_agent"):
            resolve_agent_url("nonexistent_agent", sample_registry)


# ═══════════════════════════════════════════════════════════════════════
# U7–U9: Auth / JWT resolution
# ═══════════════════════════════════════════════════════════════════════


class TestResolveJwtToken:
    """Tests for resolve_jwt_token()."""

    def test_mode_a_token_passthrough(self):
        """U7: NEXUS_JWT_TOKEN env var is used directly."""
        with patch.dict(os.environ, {"NEXUS_JWT_TOKEN": "pre-minted-token-xyz"}):
            token = resolve_jwt_token()

        assert token == "pre-minted-token-xyz"

    def test_mode_b_mint_on_startup(self):
        """U8: NEXUS_JWT_SECRET mints a decodable token."""
        env = {"NEXUS_JWT_SECRET": "test-secret-abc", "NEXUS_JWT_TOKEN": ""}
        with patch.dict(os.environ, env):
            token = resolve_jwt_token()

        assert isinstance(token, str)
        assert len(token) > 20  # JWT tokens are always long
        # Token should have 3 dot-separated parts (header.payload.signature)
        parts = token.split(".")
        assert len(parts) == 3, f"Expected JWT format, got {token[:60]}"

    def test_mode_c_default_fallback(self):
        """U9: No env vars → falls back to dev default."""
        env = {"NEXUS_JWT_TOKEN": "", "NEXUS_JWT_SECRET": ""}
        with patch.dict(os.environ, env):
            token = resolve_jwt_token()

        assert isinstance(token, str)
        assert len(token) > 20


# ═══════════════════════════════════════════════════════════════════════
# U10–U12: SSE parsing
# ═══════════════════════════════════════════════════════════════════════


class TestSseParsing:
    """Tests for parse_sse_chunk() and SseEvent."""

    def test_parse_full_sse_frame(self):
        """U10: Full SSE frame with id/event/data is parsed correctly."""
        chunk = 'id: 1\nevent: nexus.task.status\ndata: {"state": "working"}'
        evt = parse_sse_chunk(chunk)

        assert evt is not None
        assert evt.seq == 1
        assert evt.event == "nexus.task.status"
        assert evt.data == {"state": "working"}

    def test_parse_event_without_id(self):
        """U10b: SSE frame without id field still parses."""
        chunk = 'event: nexus.task.status\ndata: {"state": "accepted"}'
        evt = parse_sse_chunk(chunk)

        assert evt is not None
        assert evt.seq is None
        assert evt.event == "nexus.task.status"

    def test_parse_string_data(self):
        """U10c: Non-JSON data is returned as-is string."""
        chunk = "event: info\ndata: plain text"
        evt = parse_sse_chunk(chunk)

        assert evt is not None
        assert evt.data == "plain text"

    def test_parse_empty_chunk_returns_none(self):
        """U10d: Empty chunk returns None."""
        evt = parse_sse_chunk("")
        assert evt is None

    def test_final_event_is_terminal(self):
        """U11: nexus.task.final events are marked terminal."""
        chunk = 'event: nexus.task.final\ndata: {"result": "done"}'
        evt = parse_sse_chunk(chunk)

        assert evt is not None
        assert evt.is_terminal is True

    def test_error_event_is_terminal(self):
        """U12: nexus.task.error events are marked terminal."""
        chunk = 'event: nexus.task.error\ndata: {"error": "timeout"}'
        evt = parse_sse_chunk(chunk)

        assert evt is not None
        assert evt.is_terminal is True

    def test_status_event_not_terminal(self):
        """Status events are NOT terminal."""
        chunk = 'event: nexus.task.status\ndata: {"state": "working"}'
        evt = parse_sse_chunk(chunk)

        assert evt is not None
        assert evt.is_terminal is False


# ═══════════════════════════════════════════════════════════════════════
# U13–U17: NEXUS → MCP progress mapping
# ═══════════════════════════════════════════════════════════════════════


class TestProgressMapping:
    """Tests for map_nexus_event_to_progress()."""

    def test_monotonic_progression(self):
        """U13: Full lifecycle maps to monotonically increasing progress."""
        events = [
            SseEvent(event="nexus.task.status", data={"status": {"state": "accepted"}}),
            SseEvent(
                event="nexus.task.status", data={"status": {"state": "working", "percent": 30}}
            ),
            SseEvent(
                event="nexus.task.status", data={"status": {"state": "working", "percent": 60}}
            ),
            SseEvent(event="nexus.task.final", data={"result": "done"}),
        ]

        progress_values = []
        current = 0
        for evt in events:
            update = map_nexus_event_to_progress(evt, current)
            progress_values.append(update.progress)
            current = update.progress

        # Each value must be >= previous
        for i in range(1, len(progress_values)):
            assert progress_values[i] >= progress_values[i - 1], (
                f"Progress decreased at step {i}: {progress_values}"
            )

        # Final must be 100
        assert progress_values[-1] == 100

    def test_accepted_maps_to_zero(self):
        """U14: 'accepted' state maps to progress 0."""
        evt = SseEvent(event="nexus.task.status", data={"status": {"state": "accepted"}})
        update = map_nexus_event_to_progress(evt, 0)
        assert update.progress == 0
        assert update.description == "Task accepted"

    def test_working_with_percent(self):
        """U15: 'working' state with percent uses the percent value."""
        evt = SseEvent(
            event="nexus.task.status", data={"status": {"state": "working", "percent": 45}}
        )
        update = map_nexus_event_to_progress(evt, 0)
        assert update.progress == 45
        assert update.description == "Task working"

    def test_working_without_percent_increments(self):
        """Working state without percent increments from current."""
        evt = SseEvent(event="nexus.task.status", data={"status": {"state": "working"}})
        update = map_nexus_event_to_progress(evt, 5)
        assert update.progress > 5
        assert update.progress <= 99

    def test_final_always_100(self):
        """Final event always maps to 100."""
        evt = SseEvent(event="nexus.task.final", data={"result": "ok"})
        update = map_nexus_event_to_progress(evt, 50)
        assert update.progress == 100
        assert update.description == "Task completed"

    def test_error_near_end(self):
        """Error event maps to near-end progress (never 100)."""
        evt = SseEvent(event="nexus.task.error", data={"error": "fail"})
        update = map_nexus_event_to_progress(evt, 50)
        assert update.progress >= 50
        assert update.progress < 100
        assert update.description == "Task error"

    def test_working_capped_at_99(self):
        """Working progress never exceeds 99 (100 reserved for final)."""
        evt = SseEvent(
            event="nexus.task.status", data={"status": {"state": "working", "percent": 100}}
        )
        update = map_nexus_event_to_progress(evt, 0)
        assert update.progress <= 99
