from __future__ import annotations

from tools.helixcare_scenarios import resolve_agent_rpc_url
from tools.traffic_generator import resolve_triage_rpc_endpoint


def test_resolve_triage_rpc_endpoint_direct_mode() -> None:
    endpoint = resolve_triage_rpc_endpoint(
        triage_agent_url="http://localhost:8021",
        gateway_url="",
        triage_alias="triage",
    )
    assert endpoint == "http://localhost:8021/rpc"


def test_resolve_triage_rpc_endpoint_gateway_mode() -> None:
    endpoint = resolve_triage_rpc_endpoint(
        triage_agent_url="http://localhost:8021",
        gateway_url="http://localhost:8100",
        triage_alias="triage_agent",
    )
    assert endpoint == "http://localhost:8100/rpc/triage"


def test_resolve_agent_rpc_url_direct_mode() -> None:
    assert resolve_agent_rpc_url("pharmacy") == "http://localhost:8025/rpc"


def test_resolve_agent_rpc_url_gateway_mode() -> None:
    endpoint = resolve_agent_rpc_url("care_coordinator", gateway_url="http://localhost:8100")
    assert endpoint == "http://localhost:8100/rpc/coordinator"

