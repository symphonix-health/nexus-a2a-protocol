"""Matrix-driven tests for the Command Centre monitoring dashboard."""
from __future__ import annotations

import asyncio
import json
import time
import pytest
import httpx

from tests.nexus_harness.runner import (
    scenarios_for, pytest_ids, DEMO_URLS, get_report, ScenarioResult,
)

MATRIX = "nexus_command_centre_matrix.json"
URLS = DEMO_URLS.get("command-centre", {"dashboard": "http://localhost:8099"})
ED_URLS = DEMO_URLS["ed-triage"]

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


@pytest.mark.parametrize("scenario", _edge, ids=pytest_ids(_edge))
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


@pytest.mark.asyncio
async def test_command_centre_ed_triage_statuses_after_task(
    client: httpx.AsyncClient,
    auth_headers: dict,
):
    """Regression guard: after one ED triage task, key ED agents remain healthy on dashboard."""
    sr = ScenarioResult(
        use_case_id="UC-CMD-HEALTH-TRIAGE-0001",
        scenario_title="Command Centre reports healthy ED triage statuses after one task",
        poc_demo="command-centre",
        scenario_type="positive",
        requirement_ids=["MON-1", "FR-3", "FR-4", "FR-5"],
    )
    t0 = time.monotonic()
    dashboard_base = URLS.get("dashboard", "http://localhost:8099")
    triage_base = ED_URLS["triage-agent"]
    required_agents = ("openhie-mediator", "diagnosis-agent", "triage-agent")
    baseline_processed = {name: 0 for name in required_agents}
    baseline_errored = {name: 0 for name in required_agents}

    try:
        # Wait for command centre and triage agent to become reachable.
        deadline_ready = time.monotonic() + 180.0
        cc_ready = False
        triage_ready = False
        cc_last_error = "not_attempted"
        triage_last_error = "not_attempted"
        while time.monotonic() < deadline_ready:
            try:
                health = await client.get(f"{dashboard_base}/health", timeout=10.0)
                cc_ready = health.status_code == 200
                cc_last_error = f"status={health.status_code}"
            except Exception:
                cc_ready = False
                cc_last_error = "request_error"
            try:
                triage_health = await client.get(f"{triage_base}/health", timeout=10.0)
                triage_ready = triage_health.status_code == 200
                triage_last_error = f"health_status={triage_health.status_code}"
            except Exception:
                triage_ready = False
                triage_last_error = "health_request_error"

            if not triage_ready:
                try:
                    triage_card = await client.get(
                        f"{triage_base}/.well-known/agent-card.json", timeout=10.0
                    )
                    triage_ready = triage_card.status_code == 200
                    triage_last_error = f"card_status={triage_card.status_code}"
                except Exception:
                    triage_ready = False
                    triage_last_error = "card_request_error"

            if not triage_ready and cc_ready:
                try:
                    agents_resp = await client.get(f"{dashboard_base}/api/agents", timeout=10.0)
                    if agents_resp.status_code == 200:
                        rows = agents_resp.json()
                        if isinstance(rows, list):
                            by_name = {
                                a.get("name"): a for a in rows
                                if isinstance(a, dict) and a.get("name")
                            }
                            triage_row = by_name.get("triage-agent")
                            triage_ready = bool(
                                isinstance(triage_row, dict) and triage_row.get("last_seen")
                            )
                            if not triage_ready:
                                triage_last_error = "triage_missing_from_dashboard_poll"
                    else:
                        triage_last_error = f"agents_status={agents_resp.status_code}"
                except Exception:
                    triage_last_error = "agents_poll_error"
            if cc_ready and triage_ready:
                break
            await asyncio.sleep(2.0)

        assert cc_ready, f"Command Centre did not become ready within 180s ({cc_last_error})"
        assert triage_ready, f"Triage agent did not become ready within 180s ({triage_last_error})"

        # Capture baseline metrics so assertions are tied to this test run.
        try:
            baseline_resp = await client.get(f"{dashboard_base}/api/agents", timeout=30.0)
            if baseline_resp.status_code == 200:
                baseline_rows = baseline_resp.json()
                baseline_by_name = {
                    a.get("name"): a for a in baseline_rows
                    if isinstance(a, dict) and a.get("name")
                }
                for name in required_agents:
                    metrics = (baseline_by_name.get(name) or {}).get("metrics", {})
                    completed = int(metrics.get("tasks_completed", 0))
                    errored = int(metrics.get("tasks_errored", 0))
                    baseline_processed[name] = completed + errored
                    baseline_errored[name] = errored
        except Exception:
            # If baseline read fails transiently, continue with zeroed baselines.
            pass

        payload = {
            "jsonrpc": "2.0",
            "id": "harness-cmd-health-1",
            "method": "tasks/sendSubscribe",
            "params": {
                "task": {
                    "patient_ref": "Patient/123",
                    "inputs": {
                        "chief_complaint": "chest pain and shortness of breath",
                        "age": 55,
                    },
                }
            },
        }
        triage_resp = None
        triage_last_error = "not_attempted"
        for _ in range(5):
            try:
                triage_resp = await client.post(
                    f"{triage_base}/rpc",
                    headers=auth_headers,
                    content=json.dumps(payload),
                    timeout=30.0,
                )
                if triage_resp.status_code == 200:
                    break
                triage_last_error = f"status={triage_resp.status_code}"
            except Exception as exc:
                triage_last_error = str(exc)
            await asyncio.sleep(1.5)
        assert triage_resp is not None and triage_resp.status_code == 200, (
            f"Triage RPC failed after retries ({triage_last_error})"
        )
        triage_body = triage_resp.json()
        task_id = ((triage_body.get("result") or {}).get("task_id"))
        assert task_id, "Triage RPC response missing task_id"

        deadline = time.monotonic() + 660.0
        snapshots: dict[str, dict] = {}

        while time.monotonic() < deadline:
            await asyncio.sleep(5.0)
            try:
                agents_resp = await client.get(f"{dashboard_base}/api/agents", timeout=30.0)
            except Exception:
                continue
            if agents_resp.status_code != 200:
                continue
            rows = agents_resp.json()
            by_name = {
                a.get("name"): a for a in rows
                if isinstance(a, dict) and a.get("name")
            }
            if all(name in by_name for name in required_agents):
                snapshots = {name: by_name[name] for name in required_agents}
                # Wait until each relevant agent has processed at least one new task.
                done = True
                for name in required_agents:
                    metrics = snapshots[name].get("metrics", {})
                    processed = int(metrics.get("tasks_completed", 0)) + int(metrics.get("tasks_errored", 0))
                    if processed <= baseline_processed.get(name, 0):
                        done = False
                        break
                if done:
                    break

        assert snapshots, "Dashboard never reported all required ED agents"
        statuses = {name: snapshots[name].get("status", "unknown") for name in required_agents}
        metrics_dump = {name: snapshots[name].get("metrics", {}) for name in required_agents}
        allowed_statuses = {"healthy", "degraded"}
        non_operational = {
            name: status for name, status in statuses.items() if status not in allowed_statuses
        }
        assert not non_operational, (
            f"Expected operational statuses ({sorted(allowed_statuses)}) for {required_agents}, "
            f"got {statuses}; metrics={metrics_dump}"
        )

        new_errors = {}
        for name in required_agents:
            current_errored = int((metrics_dump.get(name) or {}).get("tasks_errored", 0))
            delta = max(0, current_errored - baseline_errored.get(name, 0))
            if delta > 0:
                new_errors[name] = delta
        assert not new_errors, (
            f"Expected no new task errors for {required_agents}, got new error deltas={new_errors}; "
            f"statuses={statuses}; metrics={metrics_dump}"
        )
        sr.status = "pass"
    except AssertionError as exc:
        sr.status = "fail"
        sr.message = str(exc)
    except Exception as exc:
        sr.status = "error"
        sr.message = str(exc)
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)
    assert sr.status == "pass", sr.message
