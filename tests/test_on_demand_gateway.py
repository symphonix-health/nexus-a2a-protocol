from __future__ import annotations

from shared.on_demand_gateway.app.main import (
    build_alias_map,
    expand_dependency_order,
    normalize_alias,
)


def _sample_config() -> dict:
    return {
        "agents": {
            "helixcare": {
                "care_coordinator": {
                    "port": 8029,
                    "path": "demos/helixcare/care-coordinator",
                    "description": "Care coordination orchestrator",
                },
                "followup_scheduler": {
                    "port": 8028,
                    "path": "demos/helixcare/followup-scheduler",
                    "description": "Follow-up scheduler",
                },
                "triage_agent": {
                    "port": 8021,
                    "path": "demos/ed-triage/triage-agent",
                    "description": "Triage agent",
                },
            }
        }
    }


def test_normalize_alias_strips_common_suffixes() -> None:
    assert normalize_alias("triage_agent") == "triage"
    assert normalize_alias("followup-scheduler") == "followup"
    assert normalize_alias("care_coordinator") == "coordinator"


def test_build_alias_map_includes_expected_alias_variants() -> None:
    alias_map = build_alias_map(_sample_config())

    assert "coordinator" in alias_map
    assert "care_coordinator" in alias_map
    assert alias_map["coordinator"].port == 8029
    assert "followup" in alias_map
    assert "followup_scheduler" in alias_map
    assert alias_map["triage"].port == 8021


def test_expand_dependency_order_returns_dependencies_before_target() -> None:
    graph = {"telehealth": ["diagnosis", "pharmacy"], "diagnosis": [], "pharmacy": []}
    order = expand_dependency_order("telehealth", graph)
    assert order[-1] == "telehealth"
    assert "diagnosis" in order[:-1]
    assert "pharmacy" in order[:-1]


def test_expand_dependency_order_rejects_cycles() -> None:
    graph = {"a": ["b"], "b": ["a"]}
    try:
        expand_dependency_order("a", graph)
    except ValueError as exc:
        assert "cycle" in str(exc).lower()
    else:
        raise AssertionError("Expected cycle detection to raise ValueError")

