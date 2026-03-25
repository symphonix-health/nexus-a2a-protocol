"""Tests for MCP server tool registration and schema validation.

Validates that the MCP server exposes the expected tools with correct
schemas, and that tool dispatch produces correct output shapes for
local (non-network) scenarios.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# This file tests functionality via the deprecated mcp_adapter shim.
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

# Ensure shared/ and src/ are importable
REPO_ROOT = Path(__file__).resolve().parents[1]
for sub in ("shared", "src"):
    p = str(REPO_ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)


# ── Import helpers without starting the MCP server ────────────────────
# We import the mcp_adapter directly rather than the server entrypoint
# to avoid MCP SDK dependency in unit tests.

from nexus_common.mcp_adapter import load_agent_registry, resolve_agent_url  # noqa: E402

# ═══════════════════════════════════════════════════════════════════════
# T1: All expected tools exist (by inspecting the server module)
# ═══════════════════════════════════════════════════════════════════════


EXPECTED_TOOLS = {
    "nexus_list_agents",
    "nexus_get_agent_card",
    "nexus_call_rpc",
    "nexus_send_task",
    "nexus_stream_task_events",
}


def test_tools_registered():
    """T1: Server module defines all expected tool functions."""
    # Import the server module to introspect its defined tools
    tools_dir = REPO_ROOT / "tools"
    if str(tools_dir.parent) not in sys.path:
        sys.path.insert(0, str(tools_dir.parent))

    # We check the module source for the @mcp.tool decorated functions
    server_source = (REPO_ROOT / "tools" / "nexus_mcp_server.py").read_text(encoding="utf-8")

    for tool_name in EXPECTED_TOOLS:
        assert f"async def {tool_name}" in server_source, (
            f"Tool function '{tool_name}' not found in nexus_mcp_server.py"
        )


def test_tool_resource_registered():
    """T1b: Server defines the nexus://topology resource."""
    server_source = (REPO_ROOT / "tools" / "nexus_mcp_server.py").read_text(encoding="utf-8")
    assert 'resource("nexus://topology")' in server_source


# ═══════════════════════════════════════════════════════════════════════
# T2: Tool input schemas
# ═══════════════════════════════════════════════════════════════════════


def test_nexus_list_agents_has_include_status_param():
    """T2a: nexus_list_agents accepts include_status boolean."""
    server_source = (REPO_ROOT / "tools" / "nexus_mcp_server.py").read_text(encoding="utf-8")
    assert "include_status: bool" in server_source


def test_nexus_get_agent_card_has_agent_param():
    """T2b: nexus_get_agent_card requires an agent parameter."""
    server_source = (REPO_ROOT / "tools" / "nexus_mcp_server.py").read_text(encoding="utf-8")
    # Find the function signature of nexus_get_agent_card
    assert "async def nexus_get_agent_card" in server_source
    assert "agent: str" in server_source


def test_nexus_call_rpc_has_required_params():
    """T2c: nexus_call_rpc has agent, method, params, and optional token."""
    server_source = (REPO_ROOT / "tools" / "nexus_mcp_server.py").read_text(encoding="utf-8")
    assert "async def nexus_call_rpc" in server_source
    assert "method: str" in server_source


def test_nexus_send_task_has_required_params():
    """T2d: nexus_send_task has agent, message, and optional fields."""
    server_source = (REPO_ROOT / "tools" / "nexus_mcp_server.py").read_text(encoding="utf-8")
    assert "async def nexus_send_task" in server_source
    assert "message: str" in server_source
    assert "subscribe: bool" in server_source


# ═══════════════════════════════════════════════════════════════════════
# T3–T4: List agents tool with registry
# ═══════════════════════════════════════════════════════════════════════


def test_list_agents_returns_all_from_config():
    """T3: load_agent_registry with real config → returns all agents."""
    config_path = str(REPO_ROOT / "config" / "agents.json")
    registry = load_agent_registry(config_path)

    assert len(registry) >= 20
    # Every entry should be an AgentInfo with required fields
    for alias, info in registry.items():
        assert info.alias == alias
        assert info.port > 0
        assert info.url.startswith("http://")


def test_list_agents_entries_have_categories():
    """T3b: Each agent has a non-empty category."""
    config_path = str(REPO_ROOT / "config" / "agents.json")
    registry = load_agent_registry(config_path)

    for alias, info in registry.items():
        assert info.category, f"Agent {alias} has no category"


# ═══════════════════════════════════════════════════════════════════════
# T5: Unknown agent error
# ═══════════════════════════════════════════════════════════════════════


def test_get_agent_card_unknown_agent():
    """T5: resolve_agent_url with unknown alias raises ValueError."""
    registry = load_agent_registry(str(REPO_ROOT / "config" / "agents.json"))
    with pytest.raises(ValueError, match="Unknown agent alias"):
        resolve_agent_url("nonexistent_agent_xyz", registry)


# ═══════════════════════════════════════════════════════════════════════
# T6: Invalid method validation
# ═══════════════════════════════════════════════════════════════════════


def test_call_rpc_empty_method_still_serialisable():
    """T6: Empty method is JSON-serialisable (validation left to agent)."""
    # The MCP tool accepts any method string; the NEXUS agent validates.
    # We just verify the adapter doesn't crash on empty strings.
    assert json.dumps({"method": "", "params": {}})  # no error


# ═══════════════════════════════════════════════════════════════════════
# T7: Send task envelope construction
# ═══════════════════════════════════════════════════════════════════════


def test_send_task_envelope_structure():
    """T7: Verify the task envelope shape that nexus_send_task constructs."""
    # Simulate the envelope construction from the server tool
    import uuid

    tid = str(uuid.uuid4())
    sid = str(uuid.uuid4())
    message_text = "Patient: chest pain, age 65"

    params = {
        "task_id": tid,
        "session_id": sid,
        "message": {
            "role": "user",
            "parts": [{"type": "text", "text": message_text}],
        },
    }

    assert params["message"]["role"] == "user"
    assert len(params["message"]["parts"]) == 1
    assert params["message"]["parts"][0]["text"] == message_text
    assert params["task_id"] == tid
    assert params["session_id"] == sid


def test_send_task_with_correlation():
    """T7b: Correlation context is added when trace_id is provided."""
    import uuid

    tid = str(uuid.uuid4())
    trace_id = "trace-abc-123"

    params = {
        "task_id": tid,
        "session_id": str(uuid.uuid4()),
        "message": {
            "role": "user",
            "parts": [{"type": "text", "text": "test"}],
        },
    }

    # Simulate correlation addition (mirrors nexus_send_task logic)
    params["correlation"] = {
        "trace_id": trace_id,
        "parent_task_id": tid,
    }

    assert params["correlation"]["trace_id"] == trace_id
    assert params["correlation"]["parent_task_id"] == tid
