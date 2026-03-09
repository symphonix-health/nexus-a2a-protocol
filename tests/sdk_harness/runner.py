"""Matrix-driven runner for SDK transport conformance scenarios."""

from __future__ import annotations

import importlib
import json
import os
import pathlib
import time
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from nexus_a2a_protocol.sdk import (
    HttpSseTransport,
    SimulationTransport,
    TransportError,
    WebSocketTransport,
    map_nexus_event_to_progress,
    resolve_jwt_token,
)

from tests.sdk_harness.mock_runtime import (
    MockNexusRuntime,
    _FASTAPI_IMPORT_ERROR,
    build_mock_ws_connect,
)

MATRICES_DIR = pathlib.Path(__file__).resolve().parents[2] / "nexus-a2a" / "artefacts" / "matrices"


@dataclass(slots=True)
class SdkScenarioResult:
    use_case_id: str
    scenario_title: str
    scenario_type: str
    transport: str
    status: str = "pending"  # pending | pass | fail | skip | error
    message: str = ""
    duration_ms: float = 0.0


@dataclass
class SdkConformanceReport:
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    results: list[SdkScenarioResult] = field(default_factory=list)

    def add(self, result: SdkScenarioResult) -> None:
        self.results.append(result)
        self.total += 1
        if result.status == "pass":
            self.passed += 1
        elif result.status == "fail":
            self.failed += 1
        elif result.status == "skip":
            self.skipped += 1
        else:
            self.errors += 1

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    def save(self, path: str | pathlib.Path) -> None:
        pathlib.Path(path).write_text(self.to_json(), encoding="utf-8")


@dataclass(slots=True)
class HarnessContext:
    mode: str
    token: str
    base_url: str
    rpc_url: str
    ws_url_template: str
    http_client: httpx.AsyncClient | None = None
    runtime: MockNexusRuntime | None = None
    ws_connect: Any | None = None


_report = SdkConformanceReport()



def get_report() -> SdkConformanceReport:
    return _report



def load_matrix(filename: str) -> list[dict[str, Any]]:
    path = MATRICES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Matrix not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError("SDK matrix must be a list of scenario rows")
    return [row for row in payload if isinstance(row, dict)]



def scenarios_for(
    filename: str,
    *,
    profile: str = "full",
) -> list[dict[str, Any]]:
    rows = load_matrix(filename)
    if profile == "smoke":
        rows = [row for row in rows if "smoke" in row.get("test_tags", [])]
    return rows



def pytest_ids(scenarios: list[dict[str, Any]]) -> list[str]:
    return [str(s.get("use_case_id") or f"scenario-{i}") for i, s in enumerate(scenarios)]


async def create_context(mode: str | None = None) -> HarnessContext:
    selected = (mode or os.getenv("SDK_HARNESS_MODE", "mock")).strip().lower()
    if selected not in {"mock", "live"}:
        raise ValueError(f"Unsupported SDK_HARNESS_MODE '{selected}'")

    if selected == "live":
        base_url = os.getenv("NEXUS_ROUTER_URL", "http://localhost:9000").strip().rstrip("/")
        rpc_url = os.getenv("NEXUS_ROUTER_RPC_URL", f"{base_url}/rpc").strip()
        ws_template = os.getenv(
            "NEXUS_WS_URL_TEMPLATE",
            "ws://localhost:9000/ws/{task_id}?token={token}",
        ).strip()
        token = resolve_jwt_token()
        return HarnessContext(
            mode="live",
            token=token,
            base_url=base_url,
            rpc_url=rpc_url,
            ws_url_template=ws_template,
            http_client=httpx.AsyncClient(timeout=30.0),
        )

    if _FASTAPI_IMPORT_ERROR is not None:
        raise RuntimeError(
            "Mock SDK harness mode requires FastAPI support in the current environment"
        ) from _FASTAPI_IMPORT_ERROR

    runtime = MockNexusRuntime(required_token="mock-token")
    app = runtime.build_app()
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://sdk-harness-mock", timeout=30.0)

    return HarnessContext(
        mode="mock",
        token=runtime.required_token,
        base_url="http://sdk-harness-mock",
        rpc_url="http://sdk-harness-mock/rpc",
        ws_url_template="ws://sdk-harness-mock/ws/{task_id}?token={token}",
        http_client=client,
        runtime=runtime,
        ws_connect=build_mock_ws_connect(runtime),
    )


async def close_context(context: HarnessContext) -> None:
    if context.http_client is not None:
        await context.http_client.aclose()



def _subsequence(expected: list[str], actual: list[str]) -> bool:
    if not expected:
        return True
    if len(expected) > len(actual):
        return False
    idx = 0
    for item in actual:
        if idx < len(expected) and item == expected[idx]:
            idx += 1
    return idx == len(expected)


async def _execute_legacy_shim_action(scenario: dict[str, Any]) -> str:
    action = str(scenario.get("input_payload", {}).get("action") or "").strip()
    if not action:
        return "no_legacy_action"

    import shared.nexus_common.mcp_adapter as legacy

    if action == "legacy_registry_load":
        config_path = str(pathlib.Path(__file__).resolve().parents[2] / "config" / "agents.json")
        registry = legacy.load_agent_registry(config_path)
        if not registry:
            raise AssertionError("legacy registry load returned empty data")
        return f"registry_size={len(registry)}"

    if action == "legacy_parse_sse":
        chunk = 'id: 1\nevent: nexus.task.status\ndata: {"status": {"state": "accepted"}}'
        evt = legacy.parse_sse_chunk(chunk)
        if evt is None or evt.event != "nexus.task.status":
            raise AssertionError("legacy parse_sse_chunk failed")
        return "sse_parse_ok"

    if action == "legacy_progress_map":
        evt = legacy.SseEvent(event="nexus.task.final", data={"ok": True}, seq=3)
        update = legacy.map_nexus_event_to_progress(evt, current_progress=50)
        if update.progress != 100:
            raise AssertionError("legacy progress mapping did not reach terminal 100")
        return "progress_map_ok"

    if action == "legacy_deprecation_warning":
        legacy = importlib.reload(legacy)
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always", DeprecationWarning)
            legacy.resolve_jwt_token()
        if not any(issubclass(item.category, DeprecationWarning) for item in captured):
            raise AssertionError("expected DeprecationWarning from legacy shim")
        return "deprecation_warning_ok"

    return f"unsupported_legacy_action={action}"


async def execute_scenario(scenario: dict[str, Any], context: HarnessContext) -> str:
    payload = scenario.get("input_payload", {})
    if not isinstance(payload, dict):
        raise AssertionError("input_payload must be an object")

    transport_name = str(scenario.get("transport") or "simulation").strip().lower()
    if transport_name == "legacy":
        return await _execute_legacy_shim_action(scenario)

    if transport_name == "simulation":
        transport = SimulationTransport(agent_id="simulation-harness")
    elif transport_name == "http_sse":
        transport = HttpSseTransport(
            context.base_url,
            token=context.token,
            client=context.http_client,
            timeout=30.0,
            agent_id="sdk-harness",
        )
    elif transport_name == "websocket":
        transport = WebSocketTransport(
            rpc_url=context.rpc_url,
            ws_url_template=context.ws_url_template,
            token=context.token,
            http_client=context.http_client,
            ws_connect=context.ws_connect,
            timeout=30.0,
            agent_id="sdk-harness",
        )
    else:
        raise AssertionError(f"unsupported transport {transport_name}")

    await transport.connect()
    action = str(payload.get("action") or "send_and_stream").strip()
    expected = scenario.get("expected_result", {})
    if not isinstance(expected, dict):
        expected = {}

    try:
        if action == "send_invalid_method":
            try:
                request_payload = {
                    "method": "tasks/invalid",
                    "params": payload.get("params", {}),
                }
                if "token_override" in payload:
                    request_payload["token"] = payload.get("token_override")
                await transport.send_task(request_payload)
            except TransportError as exc:
                expected_code = expected.get("error_code")
                if isinstance(expected_code, int) and exc.code != expected_code:
                    raise AssertionError(f"expected error_code {expected_code}, got {exc.code}")
                return f"error={exc.code}"
            raise AssertionError("expected TransportError")

        if action == "send_expect_auth_failure":
            try:
                request_payload = {
                    "method": payload.get("method", "tasks/send"),
                    "params": payload.get("params", {}),
                }
                if "token_override" in payload:
                    request_payload["token"] = payload.get("token_override")
                await transport.send_task(request_payload)
            except TransportError as exc:
                if exc.http_status not in {401, None}:
                    raise AssertionError(f"expected auth-related status, got {exc.http_status}")
                return "auth_failed"
            raise AssertionError("expected auth failure")

        if action == "send_twice_idempotent":
            method = str(payload.get("method") or "tasks/send")
            params = payload.get("params", {}) if isinstance(payload.get("params"), dict) else {}
            first = await transport.send_task({"method": method, "params": params})
            second = await transport.send_task({"method": method, "params": params})
            if first.task_id != second.task_id:
                raise AssertionError("idempotent replay returned different task_id")
            return f"task_id={first.task_id}"

        method = str(payload.get("method") or "tasks/sendSubscribe")
        params = payload.get("params", {}) if isinstance(payload.get("params"), dict) else {}
        request_payload = {
            "method": method,
            "params": params,
        }
        if "token_override" in payload:
            request_payload["token"] = payload.get("token_override")
        submission = await transport.send_task(request_payload)

        if expected.get("has_task_id", True) and not submission.task_id:
            raise AssertionError("missing task_id")

        if action == "send_only":
            return f"task_id={submission.task_id}"

        events: list[Any] = []
        max_events_raw = payload.get("max_events")
        if max_events_raw is None and isinstance(params, dict):
            max_events_raw = params.get("max_events")
        max_events_is_explicit = max_events_raw is not None
        try:
            max_events = int(max_events_raw) if max_events_raw is not None else 20
        except Exception:
            max_events = 20
        max_events = max(1, max_events)
        async for evt in transport.stream_events(submission.task_id):
            events.append(evt)
            if len(events) >= max_events:
                break

        event_types = [evt.type for evt in events]
        expected_events = scenario.get("expected_events", [])
        if isinstance(expected_events, list) and expected_events:
            if not _subsequence([str(x) for x in expected_events], event_types):
                raise AssertionError(
                    f"event mismatch expected subsequence={expected_events}, actual={event_types}"
                )

        if expected.get("progress_monotonic"):
            current = 0
            for evt in events:
                mapped = map_nexus_event_to_progress(evt, current)
                if mapped.progress < current:
                    raise AssertionError("progress decreased")
                current = mapped.progress

        if expected.get("terminal") == "error":
            if not events or events[-1].type != "nexus.task.error":
                if not (max_events_is_explicit and len(events) >= max_events):
                    raise AssertionError("expected terminal error event")
        if expected.get("terminal") == "final":
            if not events or events[-1].type != "nexus.task.final":
                if not (max_events_is_explicit and len(events) >= max_events):
                    raise AssertionError("expected terminal final event")

        return f"events={len(events)}"
    finally:
        await transport.stop()
