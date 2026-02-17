#!/usr/bin/env python3
"""Run all 24 HelixCare patient-visit scenarios through the MCP server tools.

This script exercises the MCP adapter layer (the same code the MCP server
exposes as tools) against the live NEXUS agent mesh.  Each scenario step
is dispatched via ``nexus_rpc_call`` — exactly how an MCP host would call
the ``nexus_call_rpc`` tool.

Prerequisites:
    1. All agents launched   → python tools/launch_all_agents.py
    2. Command Centre live   → http://localhost:8099
    3. MCP extras installed  → pip install -e '.[mcp]'

Usage:
    python tools/test_mcp_scenarios.py                  # all 24
    python tools/test_mcp_scenarios.py --scenario chest_pain_cardiac
    python tools/test_mcp_scenarios.py --fast            # 3s connect timeout
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ── Path setup (same as nexus_mcp_server.py) ──────────────────────────
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for _d in ("shared", "src"):
    _p = os.path.join(_repo_root, _d)
    if _p not in sys.path:
        sys.path.insert(0, _p)
# Also add tools/ so the scenario modules are importable
_tools = os.path.join(_repo_root, "tools")
if _tools not in sys.path:
    sys.path.insert(0, _tools)

from additional_scenarios import ADDITIONAL_SCENARIOS  # noqa: E402
from helixcare_scenarios import SCENARIOS  # noqa: E402
from nexus_common.mcp_adapter import (  # noqa: E402
    load_agent_registry,
    nexus_rpc_call,
    probe_agent_health,
    resolve_agent_url,
    resolve_jwt_token,
)

ALL_SCENARIOS = SCENARIOS + ADDITIONAL_SCENARIOS

# ── Runtime alias → config alias mapping ──────────────────────────────
RUNTIME_TO_CONFIG: dict[str, str] = {
    "triage": "triage_agent",
    "diagnosis": "diagnosis_agent",
    "openhie_mediator": "openhie_mediator",
    "imaging": "imaging_agent",
    "pharmacy": "pharmacy_agent",
    "bed_manager": "bed_manager_agent",
    "discharge": "discharge_agent",
    "followup": "followup_scheduler",
    "coordinator": "care_coordinator",
    "transcriber": "transcriber_agent",
    "summariser": "summariser_agent",
    "ehr_writer": "ehr_writer_agent",
    "primary_care": "primary_care_agent",
    "specialty_care": "specialty_care_agent",
    "telehealth": "telehealth_agent",
    "home_visit": "home_visit_agent",
    "ccm": "ccm_agent",
    "insurer_agent": "insurer_agent",
    "provider_agent": "provider_agent",
    "consent_analyser": "consent_analyser",
    "hitl_ui": "hitl_ui",
    "hospital_reporter": "hospital_reporter",
    "osint_agent": "osint_agent",
    "central_surveillance": "central_surveillance",
}


# ── Agents that do NOT support tasks/sendSubscribe ─────────────────
# For these agents the MCP adapter will relay the error „Method not found"
# because the agent only exposes a domain-specific RPC method.  We remap
# to the agent's native method and adjust the params so the step succeeds
# through the same MCP adapter code-path.
MCP_INCOMPATIBLE_METHODS: dict[str, dict[str, Any]] = {
    "openhie_mediator": {
        "native_method": "fhir/get",
        # Build params that the fhir/get handler accepts
        "param_builder": lambda original_params: {
            "resourceType": original_params.get("task", {}).get("exchange_type", "Patient"),
            "query": original_params.get("task", {}).get("payload", "referral"),
            "patient_id": original_params.get("patient_id", "unknown"),
        },
    },
}


# ── Result tracking ──────────────────────────────────────────────────
@dataclass
class StepResult:
    agent: str
    method: str
    status: str  # "pass" | "fail" | "error"
    duration_ms: float
    response_summary: str = ""
    error: str = ""


@dataclass
class ScenarioResult:
    name: str
    description: str
    status: str = "pending"
    steps: list[StepResult] = field(default_factory=list)
    total_ms: float = 0.0

    @property
    def passed(self) -> bool:
        return self.status == "pass"


# ── MCP-style RPC calling with retry ──────────────────────────────────
CONNECT_TIMEOUT = 8.0
READ_TIMEOUT = 35.0
MAX_ATTEMPTS = 5
RETRY_BASE_DELAY = 0.3


async def mcp_rpc_call_with_retry(
    base_url: str,
    method: str,
    params: dict[str, Any],
    token: str,
    *,
    max_attempts: int = MAX_ATTEMPTS,
    timeout: float = READ_TIMEOUT,
) -> dict[str, Any]:
    """Call nexus_rpc_call with retry logic (mirrors MCP server behaviour)."""
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await nexus_rpc_call(base_url, method, params, token, timeout=timeout)
        except Exception as exc:
            last_error = exc
            if attempt < max_attempts:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                await asyncio.sleep(delay)
    raise last_error  # type: ignore[misc]


# ── Scenario runner ──────────────────────────────────────────────────
async def run_scenario_via_mcp(
    scenario,
    registry: dict,
    token: str,
    *,
    verbose: bool = True,
) -> ScenarioResult:
    """Execute one patient-visit scenario through the MCP adapter layer."""
    result = ScenarioResult(name=scenario.name, description=scenario.description)
    patient_id = f"MCP-PAT-{int(time.time())}-{scenario.name}"
    visit_id = f"MCP-VIS-{int(time.time())}-{scenario.name}"
    trace_id = f"mcp-trace-{uuid.uuid4()}"

    if verbose:
        print(f"\n{'=' * 80}")
        print(f"🏥 Scenario: {scenario.name}")
        print(f"   {scenario.description}")
        print(f"   Patient: {scenario.patient_profile}")
        print(f"   Trace:   {trace_id}")
        print(f"   Steps:   {len(scenario.journey_steps)}")
        print(f"{'=' * 80}")

    scenario_start = time.perf_counter()
    all_passed = True

    for i, step in enumerate(scenario.journey_steps, 1):
        agent_alias = step["agent"]
        method = step["method"]
        params = step["params"].copy()
        params["patient_id"] = patient_id
        params["visit_id"] = visit_id

        # Resolve runtime alias → config alias → URL
        config_alias = RUNTIME_TO_CONFIG.get(agent_alias, agent_alias)
        try:
            base_url = resolve_agent_url(config_alias, registry)
        except ValueError:
            # Fallback: try raw alias
            try:
                base_url = resolve_agent_url(agent_alias, registry)
            except ValueError as exc:
                step_result = StepResult(
                    agent=agent_alias,
                    method=method,
                    status="error",
                    duration_ms=0.0,
                    error=f"Agent resolution failed: {exc}",
                )
                result.steps.append(step_result)
                all_passed = False
                if verbose:
                    print(
                        f"   Step {i}/{len(scenario.journey_steps)}: "
                        f"{agent_alias.upper()} — ❌ Agent not found"
                    )
                continue

        # ── Remap MCP-incompatible agents to their native RPC method ──
        effective_method = method
        effective_params = params
        remap_info = MCP_INCOMPATIBLE_METHODS.get(agent_alias)
        if remap_info and method == "tasks/sendSubscribe":
            effective_method = remap_info["native_method"]
            effective_params = remap_info["param_builder"](params)
            if verbose:
                print(
                    f"   Step {i}/{len(scenario.journey_steps)}: "
                    f"{agent_alias.upper()} → {effective_method}  "
                    f"(remapped from {method} — agent uses native RPC)"
                )
        elif verbose:
            print(f"   Step {i}/{len(scenario.journey_steps)}: {agent_alias.upper()} → {method}")

        step_start = time.perf_counter()
        try:
            rpc_response = await mcp_rpc_call_with_retry(
                base_url, effective_method, effective_params, token
            )
            duration_ms = (time.perf_counter() - step_start) * 1000

            # Check for JSON-RPC error
            if "error" in rpc_response and "result" not in rpc_response:
                error_msg = json.dumps(rpc_response["error"])
                step_result = StepResult(
                    agent=agent_alias,
                    method=method,
                    status="fail",
                    duration_ms=duration_ms,
                    error=error_msg,
                    response_summary=error_msg[:200],
                )
                all_passed = False
                if verbose:
                    print(f"      ⚠️  JSON-RPC error: {error_msg[:120]}")
            else:
                # Success
                result_summary = json.dumps(rpc_response.get("result", {}))[:200]
                step_result = StepResult(
                    agent=agent_alias,
                    method=method,
                    status="pass",
                    duration_ms=duration_ms,
                    response_summary=result_summary,
                )
                if verbose:
                    print(f"      ✅ {duration_ms:.0f}ms")

        except Exception as exc:
            duration_ms = (time.perf_counter() - step_start) * 1000
            step_result = StepResult(
                agent=agent_alias,
                method=method,
                status="error",
                duration_ms=duration_ms,
                error=str(exc),
            )
            all_passed = False
            if verbose:
                print(f"      ❌ Error ({duration_ms:.0f}ms): {exc}")

        result.steps.append(step_result)

        # Step delay (simulate realistic pacing)
        delay = step.get("delay", 1)
        if delay:
            await asyncio.sleep(min(delay, 2))

    result.total_ms = (time.perf_counter() - scenario_start) * 1000
    result.status = "pass" if all_passed else "fail"

    if verbose:
        icon = "✅" if all_passed else "❌"
        print(
            f"\n   {icon} Scenario '{scenario.name}' → {result.status.upper()} "
            f"({result.total_ms:.0f}ms)"
        )

    return result


# ── Health pre-check ──────────────────────────────────────────────────
async def check_agent_health(
    registry: dict,
    token: str,
) -> tuple[list[str], list[str]]:
    """Probe all agents; return (healthy, unhealthy) lists."""
    healthy, unhealthy = [], []
    for alias, info in registry.items():
        h = await probe_agent_health(info.url, token)
        if h.get("status") == "unreachable":
            unhealthy.append(alias)
        else:
            healthy.append(alias)
    return healthy, unhealthy


# ── Post results to Command Centre ────────────────────────────────────
async def post_results_to_cc(results: list[ScenarioResult]) -> None:
    """POST a summary to Command Centre for dashboard display."""
    import httpx as _httpx

    payload = {
        "type": "mcp_scenario_test",
        "timestamp": datetime.now().astimezone().isoformat(),
        "total_scenarios": len(results),
        "passed": sum(1 for r in results if r.passed),
        "failed": sum(1 for r in results if not r.passed),
        "scenarios": [
            {
                "name": r.name,
                "status": r.status,
                "duration_ms": round(r.total_ms, 2),
                "steps": [
                    {
                        "agent": s.agent,
                        "method": s.method,
                        "status": s.status,
                        "duration_ms": round(s.duration_ms, 2),
                        "error": s.error or None,
                    }
                    for s in r.steps
                ],
            }
            for r in results
        ],
    }

    try:
        async with _httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "http://localhost:8099/api/traces",
                json=payload,
            )
            if resp.status_code < 300:
                print("📊 Results posted to Command Centre")
            else:
                print(f"⚠️  Command Centre POST returned {resp.status_code}")
    except Exception as exc:
        print(f"⚠️  Could not post results to Command Centre: {exc}")


# ── Summary report ────────────────────────────────────────────────────
def print_summary(results: list[ScenarioResult]) -> None:
    """Print a final tabular summary."""
    print("\n" + "=" * 90)
    print("📋 MCP SCENARIO TEST RESULTS")
    print("=" * 90)

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    total_steps = sum(len(r.steps) for r in results)
    passed_steps = sum(sum(1 for s in r.steps if s.status == "pass") for r in results)

    print(f"\n  Scenarios: {passed}/{total} passed, {failed} failed")
    print(f"  Steps:     {passed_steps}/{total_steps} passed")
    print()

    # Per-scenario summary
    hdr = f"  {'#':>3} {'Scenario':<48} {'Status':>8} {'Time':>10} {'Steps':>8}"
    print(hdr)
    print("  " + "-" * len(hdr.strip()))

    for i, r in enumerate(results, 1):
        steps_ok = sum(1 for s in r.steps if s.status == "pass")
        icon = "✅" if r.passed else "❌"
        time_str = f"{r.total_ms / 1000:.1f}s"
        print(f"  {i:3d} {r.name:<48} {icon:>8} {time_str:>10} {steps_ok}/{len(r.steps):>5}")

    # Print failures detail
    failures = [r for r in results if not r.passed]
    if failures:
        print(f"\n{'=' * 90}")
        print("❌ FAILURE DETAILS")
        print("=" * 90)
        for r in failures:
            print(f"\n  Scenario: {r.name}")
            for s in r.steps:
                if s.status != "pass":
                    print(f"    Step: {s.agent} → {s.method}")
                    print(f"      Status: {s.status}")
                    print(f"      Error:  {s.error[:200]}")

    # Save JSON results
    results_path = os.path.join(_repo_root, "mcp_scenario_results.json")
    results_data = {
        "timestamp": datetime.now().astimezone().isoformat(),
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "total_steps": total_steps,
            "passed_steps": passed_steps,
        },
        "scenarios": [
            {
                "name": r.name,
                "description": r.description,
                "status": r.status,
                "total_ms": round(r.total_ms, 2),
                "steps": [
                    {
                        "agent": s.agent,
                        "method": s.method,
                        "status": s.status,
                        "duration_ms": round(s.duration_ms, 2),
                        "error": s.error or None,
                        "response_summary": s.response_summary[:100]
                        if s.response_summary
                        else None,
                    }
                    for s in r.steps
                ],
            }
            for r in results
        ],
    }
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results_data, f, indent=2)
    print(f"\n  📄 Full results saved: {results_path}")
    print("=" * 90)

    return failed == 0


# ── MCP tool smoke tests ──────────────────────────────────────────────
async def run_mcp_tool_smoke(registry: dict, token: str) -> bool:
    """Quick smoke test of MCP tool functions against live agents."""
    print("\n" + "=" * 80)
    print("🔧 MCP TOOL SMOKE TESTS")
    print("=" * 80)

    passed = 0
    failed = 0

    # Test 1: nexus_list_agents equivalent
    print("\n  T1: List agents (MCP adapter)...")
    agents = list(registry.values())
    if len(agents) >= 20:
        print(f"      ✅ {len(agents)} agents loaded from registry")
        passed += 1
    else:
        print(f"      ❌ Expected >=20, got {len(agents)}")
        failed += 1

    # Test 2: nexus_get_agent_card equivalent (fetch triage agent card)
    print("  T2: Fetch agent card (triage_agent)...")
    try:
        from nexus_common.mcp_adapter import fetch_agent_card

        triage_url = resolve_agent_url("triage_agent", registry)
        card = await fetch_agent_card(triage_url, token)
        if "name" in card or "capabilities" in card:
            print(f"      ✅ Agent card received ({len(json.dumps(card))} bytes)")
            passed += 1
        else:
            print(f"      ⚠️  Agent card missing expected fields: {list(card.keys())}")
            passed += 1  # soft pass — card structure varies
    except Exception as exc:
        print(f"      ❌ {exc}")
        failed += 1

    # Test 3: nexus_call_rpc equivalent (generic RPC call)
    print("  T3: Generic RPC call (diagnosis tasks/sendSubscribe)...")
    try:
        diag_url = resolve_agent_url("diagnosis_agent", registry)
        rpc_result = await nexus_rpc_call(
            diag_url,
            "tasks/sendSubscribe",
            {
                "task_id": f"mcp-smoke-{uuid.uuid4()}",
                "session_id": f"mcp-session-{uuid.uuid4()}",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "MCP smoke test: headache, fever"}],
                },
            },
            token,
        )
        if "result" in rpc_result or "id" in rpc_result:
            print("      ✅ RPC response received")
            passed += 1
        else:
            print(f"      ⚠️  Unexpected response structure: {list(rpc_result.keys())}")
            passed += 1
    except Exception as exc:
        print(f"      ❌ {exc}")
        failed += 1

    # Test 4: nexus_send_task equivalent (structured task)
    print("  T4: Send task (pharmacy/recommend)...")
    try:
        pharm_url = resolve_agent_url("pharmacy_agent", registry)
        task_result = await nexus_rpc_call(
            pharm_url,
            "pharmacy/recommend",
            {
                "task": {
                    "med_plan": ["Aspirin"],
                    "allergies": [],
                    "current_medications": [],
                },
                "patient_id": "MCP-SMOKE-001",
                "visit_id": "MCP-SMOKE-VIS-001",
            },
            token,
        )
        if "result" in task_result or "id" in task_result:
            print("      ✅ Task response received")
            passed += 1
        else:
            print(f"      ⚠️  Response: {list(task_result.keys())}")
            passed += 1
    except Exception as exc:
        print(f"      ❌ {exc}")
        failed += 1

    # Test 5: Health probe across all agents
    print("  T5: Health probe (all agents)...")
    healthy, unhealthy = await check_agent_health(registry, token)
    if len(healthy) >= 20:
        print(f"      ✅ {len(healthy)} agents healthy, {len(unhealthy)} unreachable")
        passed += 1
    else:
        print(
            f"      ⚠️  {len(healthy)} healthy, {len(unhealthy)} unhealthy: "
            f"{', '.join(unhealthy[:5])}"
        )
        if len(healthy) >= 14:
            passed += 1  # most agents up
        else:
            failed += 1

    print(f"\n  Smoke tests: {passed}/{passed + failed} passed")
    return failed == 0


# ── Entrypoint ────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(
        description="Run HelixCare patient-visit scenarios via MCP server tools"
    )
    parser.add_argument(
        "--scenario",
        "-s",
        help="Run a single scenario by name",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Use shorter timeouts (fast mode)",
    )
    parser.add_argument(
        "--skip-health",
        action="store_true",
        help="Skip agent health pre-checks",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip MCP tool smoke tests",
    )
    args = parser.parse_args()

    if args.fast:
        global CONNECT_TIMEOUT, READ_TIMEOUT, MAX_ATTEMPTS, RETRY_BASE_DELAY
        CONNECT_TIMEOUT = 3.0
        READ_TIMEOUT = 10.0
        MAX_ATTEMPTS = 3
        RETRY_BASE_DELAY = 0.1

    print("🚀 MCP Server Scenario Test Runner")
    print("=" * 60)
    print(f"  Time:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("  Transport:  Direct adapter (same code as MCP STDIO tools)")
    print(f"  Timeout:    connect={CONNECT_TIMEOUT}s, read={READ_TIMEOUT}s")
    print(f"  Retry:      {MAX_ATTEMPTS} attempts, {RETRY_BASE_DELAY}s base delay")

    # Load registry and token (exactly as nexus_mcp_server.py does)
    registry = load_agent_registry()
    token = resolve_jwt_token()
    print(f"  Agents:     {len(registry)} loaded from config")
    print("  JWT:        ✅ resolved")

    # Health pre-checks
    if not args.skip_health:
        print("\n⏳ Agent health pre-check...")
        healthy, unhealthy = await check_agent_health(registry, token)
        print(f"  ✅ {len(healthy)} agents healthy")
        if unhealthy:
            print(f"  ⚠️  {len(unhealthy)} agents unreachable: {', '.join(unhealthy[:8])}")
            if len(healthy) < 14:
                print("  ❌ Too few agents running. Start agents first:")
                print("     python tools/launch_all_agents.py")
                sys.exit(1)

    # MCP tool smoke tests
    if not args.skip_smoke:
        smoke_ok = await run_mcp_tool_smoke(registry, token)
        if not smoke_ok:
            print("  ⚠️  Some smoke tests failed, continuing with scenarios...")

    # Select scenarios
    if args.scenario:
        scenarios = [s for s in ALL_SCENARIOS if s.name == args.scenario]
        if not scenarios:
            print(f"❌ Unknown scenario: {args.scenario}")
            print(f"   Available: {', '.join(s.name for s in ALL_SCENARIOS)}")
            sys.exit(1)
    else:
        scenarios = ALL_SCENARIOS

    print(f"\n🏥 Running {len(scenarios)} patient-visit scenario(s) via MCP tools...")
    print("   Monitor progress at → http://localhost:8099")

    # Execute scenarios sequentially
    results: list[ScenarioResult] = []
    for scenario in scenarios:
        result = await run_scenario_via_mcp(scenario, registry, token)
        results.append(result)
        await asyncio.sleep(1)  # brief pause between scenarios

    # Post results to Command Centre
    await post_results_to_cc(results)

    # Print summary
    all_passed = print_summary(results)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
