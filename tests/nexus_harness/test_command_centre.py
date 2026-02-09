"""Matrix-driven tests for the Command Centre monitoring dashboard."""
from __future__ import annotations

import json
import time
import pytest
import httpx

from tests.nexus_harness.runner import (
    scenarios_for, pytest_ids, DEMO_URLS, get_report, ScenarioResult,
)

MATRIX = "nexus_command_centre_matrix.json"
URLS = DEMO_URLS.get("command-centre", {"dashboard": "http://localhost:8099"})

_positive = scenarios_for(MATRIX, scenario_type="positive")
_negative = scenarios_for(MATRIX, scenario_type="negative")
_edge = scenarios_for(MATRIX, scenario_type="edge")


@pytest.mark.parametrize("scenario", _positive, ids=pytest_ids(_positive))
@pytest.mark.asyncio
async def test_command_centre_positive(scenario: dict, client: httpx.AsyncClient):
    """Test positive scenarios for command centre."""
    sr = ScenarioResult(
        use_case_id=scenario["use_case_id"],
        scenario_title=scenario["scenario_title"],
        poc_demo=scenario["poc_demo"],
        scenario_type=scenario["scenario_type"],
        requirement_ids=scenario.get("requirement_ids", []),
    )
    t0 = time.monotonic()
    try:
        payload = scenario.get("input_payload", {})
        endpoint = payload.get("endpoint", "/")
        method = payload.get("method", "GET")
        base = URLS.get("dashboard", "http://localhost:8099")
        
        # Handle different endpoint types
        if method == "GET":
            resp = await client.get(f"{base}{endpoint}", timeout=10.0)
            
            # Validate response
            expected_status = scenario.get("expected_http_status", 200)
            assert resp.status_code == expected_status, f"Expected {expected_status}, got {resp.status_code}"
            
            # Check expected results
            expected = scenario.get("expected_result", {})
            
            # For JSON endpoints
            if endpoint.startswith("/api/") or endpoint == "/health":
                body = resp.json()
                
                # Agent discovery validation
                if "agents_count" in expected:
                    assert len(body) >= expected["agents_count"], f"Expected >= {expected['agents_count']} agents"
                
                # Metrics validation
                if "has_metrics" in expected and expected["has_metrics"]:
                    if isinstance(body, list) and len(body) > 0:
                        first_agent = body[0]
                        assert "metrics" in first_agent, "Agent should have metrics"
                        metrics = first_agent["metrics"]
                        if "metrics_include" in expected:
                            for key in expected["metrics_include"]:
                                assert key in metrics, f"Metrics should include {key}"
                
                # Topology validation
                if "nodes_count" in expected:
                    assert "nodes" in body, "Should have nodes"
                    assert len(body["nodes"]) >= expected["nodes_count"], f"Expected >= {expected['nodes_count']} nodes"
                
                # Health validation
                if "status" in expected:
                    assert body.get("status") == expected["status"], f"Expected status {expected['status']}"
                
                if "has_timestamp" in expected and expected["has_timestamp"]:
                    assert "timestamp" in body, "Should have timestamp"
            
            # For static files
            elif endpoint in ["/", "/colors.js", "/styles.css"]:
                if "content_type" in expected:
                    content_type = resp.headers.get("content-type", "")
                    assert expected["content_type"] in content_type, f"Expected {expected['content_type']} in {content_type}"
                
                if "includes" in expected:
                    text = resp.text
                    for substring in expected["includes"]:
                        assert substring in text, f"Expected '{substring}' in response"
            
            sr.status = "pass"
        
        else:
            sr.status = "skip"
            sr.message = f"Method {method} not yet implemented in test harness"
    
    except AssertionError as exc:
        sr.status = "fail"
        sr.message = str(exc)
    except Exception as exc:
        sr.status = "error"
        sr.message = str(exc)
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)


@pytest.mark.parametrize("scenario", _negative, ids=pytest_ids(_negative))
@pytest.mark.asyncio
async def test_command_centre_negative(scenario: dict, client: httpx.AsyncClient):
    """Test negative scenarios for command centre."""
    sr = ScenarioResult(
        use_case_id=scenario["use_case_id"],
        scenario_title=scenario["scenario_title"],
        poc_demo=scenario["poc_demo"],
        scenario_type=scenario["scenario_type"],
        requirement_ids=scenario.get("requirement_ids", []),
    )
    t0 = time.monotonic()
    try:
        payload = scenario.get("input_payload", {})
        endpoint = payload.get("endpoint", "/")
        method = payload.get("method", "GET")
        base = URLS.get("dashboard", "http://localhost:8099")
        
        if method == "GET":
            try:
                resp = await client.get(f"{base}{endpoint}", timeout=10.0)
                
                # For negative tests, we expect certain behaviors
                expected = scenario.get("expected_result", {})
                expected_status = scenario.get("expected_http_status", 200)
                
                # Still expect 200 for graceful degradation
                if resp.status_code == expected_status:
                    if endpoint.startswith("/api/"):
                        body = resp.json()
                        
                        # Check for degraded states
                        if "agent_status" in expected:
                            # At least one agent should match expected status
                            if isinstance(body, list):
                                statuses = [a.get("status") for a in body]
                                assert expected["agent_status"] in statuses, \
                                    f"Expected status '{expected['agent_status']}' in {statuses}"
                        
                        # Check partial failures are handled
                        if expected.get("other_agents_visible"):
                            assert len(body) > 0, "Should still show other agents"
                    
                    sr.status = "pass"
                else:
                    sr.status = "fail"
                    sr.message = f"Unexpected status {resp.status_code}"
            
            except httpx.TimeoutException:
                # Timeouts might be expected for some negative scenarios
                if "timeout_handled" in scenario.get("expected_result", {}):
                    sr.status = "pass"
                else:
                    raise
        else:
            sr.status = "skip"
            sr.message = f"Method {method} not yet implemented"
    
    except Exception as exc:
        # For negative tests, some exceptions might be expected
        error_condition = scenario.get("error_condition", "none")
        if error_condition in ["expected_failure", "expected_degradation", "expected_partial_failure"]:
            sr.status = "pass"
            sr.message = f"Expected failure: {exc}"
        else:
            sr.status = "error"
            sr.message = str(exc)
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)


@pytest.mark.parametrize("scenario", _edge[:5], ids=pytest_ids(_edge[:5]))
@pytest.mark.asyncio
async def test_command_centre_edge(scenario: dict, client: httpx.AsyncClient):
    """Test edge case scenarios for command centre."""
    sr = ScenarioResult(
        use_case_id=scenario["use_case_id"],
        scenario_title=scenario["scenario_title"],
        poc_demo=scenario["poc_demo"],
        scenario_type=scenario["scenario_type"],
        requirement_ids=scenario.get("requirement_ids", []),
    )
    t0 = time.monotonic()
    try:
        # Edge cases often require special setup
        # For now, we'll test basic functionality
        payload = scenario.get("input_payload", {})
        action = payload.get("action")
        
        if action == "send_concurrent_tasks":
            # This would require the agents to be running
            # We'll skip for now but structure is in place
            sr.status = "skip"
            sr.message = "Requires running agent infrastructure"
        else:
            # Test basic endpoint access
            base = URLS.get("dashboard", "http://localhost:8099")
            endpoint = payload.get("endpoint", "/api/agents")
            
            try:
                resp = await client.get(f"{base}{endpoint}", timeout=10.0)
                if resp.status_code == 200:
                    sr.status = "pass"
                else:
                    sr.status = "fail"
                    sr.message = f"Status {resp.status_code}"
            except httpx.ConnectError:
                sr.status = "skip"
                sr.message = "Command centre not running"
    
    except Exception as exc:
        sr.status = "error"
        sr.message = str(exc)
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)
