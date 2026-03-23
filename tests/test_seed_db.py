"""Tests for the central seed database module."""

from __future__ import annotations

from pathlib import Path

import pytest
from shared.nexus_common.seed_db import NexusSeedDB, _agent_id_to_alias

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS_JSON = REPO_ROOT / "config" / "agents.json"
PERSONAS_JSON = REPO_ROOT / "config" / "personas.json"
AGENT_PERSONAS_JSON = REPO_ROOT / "config" / "agent_personas.json"
SCENARIOS_JSON = REPO_ROOT / "tools" / "helixcare_all_scenarios.json"
DEP_GRAPH_JSON = REPO_ROOT / "config" / "dependency_graph.json"


@pytest.fixture()
def seed_db(tmp_path: Path) -> NexusSeedDB:
    """Create a fresh seed DB in a temp directory and seed it."""
    db_path = str(tmp_path / "test_seed.sqlite3")
    db = NexusSeedDB(path=db_path)
    db.seed_all()
    return db


# ── Alias normalisation ─────────────────────────────────────────────────


class TestAliasNormalisation:
    def test_strips_agent_suffix(self):
        assert _agent_id_to_alias("triage_agent") == "triage"
        assert _agent_id_to_alias("imaging_agent") == "imaging"

    def test_override_care_coordinator(self):
        assert _agent_id_to_alias("care_coordinator") == "coordinator"

    def test_override_followup_scheduler(self):
        assert _agent_id_to_alias("followup_scheduler") == "followup"

    def test_keeps_suffix_for_special_ids(self):
        assert _agent_id_to_alias("insurer_agent") == "insurer_agent"
        assert _agent_id_to_alias("provider_agent") == "provider_agent"

    def test_passthrough_no_suffix(self):
        assert _agent_id_to_alias("hitl_ui") == "hitl_ui"
        assert _agent_id_to_alias("consent_analyser") == "consent_analyser"


# ── Schema creation ──────────────────────────────────────────────────────


def test_seed_db_creates_tables(tmp_path: Path):
    db_path = str(tmp_path / "schema_test.sqlite3")
    db = NexusSeedDB(path=db_path)
    # Verify tables exist by querying sqlite_master
    rows = db._backend.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    table_names = {r[0] for r in rows}
    expected = {
        "agents",
        "agent_personas",
        "personas",
        "scenarios",
        "triage_rules",
        "dependency_graph",
    }
    assert expected.issubset(table_names)
    db.close()


# ── Seed agents ──────────────────────────────────────────────────────────


class TestSeedAgents:
    def test_seed_agents_from_config(self, seed_db: NexusSeedDB):
        urls = seed_db.get_all_agent_urls()
        assert len(urls) >= 25, f"Expected at least 25 agents, got {len(urls)}"

    def test_known_ports(self, seed_db: NexusSeedDB):
        assert seed_db.get_agent_url("triage") == "http://localhost:8021"
        assert seed_db.get_agent_url("diagnosis") == "http://localhost:8022"
        assert seed_db.get_agent_url("pharmacy") == "http://localhost:8025"
        assert seed_db.get_agent_url("clinician_avatar") == "http://localhost:8039"

    def test_coordinator_alias(self, seed_db: NexusSeedDB):
        assert seed_db.get_agent_url("coordinator") == "http://localhost:8029"

    def test_followup_alias(self, seed_db: NexusSeedDB):
        assert seed_db.get_agent_url("followup") == "http://localhost:8028"

    def test_unknown_alias_returns_none(self, seed_db: NexusSeedDB):
        assert seed_db.get_agent_url("nonexistent_agent") is None

    def test_backend_gateway_excluded_from_agent_urls(self, seed_db: NexusSeedDB):
        urls = seed_db.get_all_agent_urls()
        assert "command_centre" not in urls
        assert "on_demand_gateway" not in urls

    def test_matches_old_base_urls(self, seed_db: NexusSeedDB):
        """Verify DB produces the same URL map as the old hardcoded BASE_URLS."""
        old_base_urls = {
            "triage": "http://localhost:8021",
            "diagnosis": "http://localhost:8022",
            "openhie_mediator": "http://localhost:8023",
            "imaging": "http://localhost:8024",
            "pharmacy": "http://localhost:8025",
            "bed_manager": "http://localhost:8026",
            "discharge": "http://localhost:8027",
            "followup": "http://localhost:8028",
            "coordinator": "http://localhost:8029",
            "transcriber": "http://localhost:8031",
            "summariser": "http://localhost:8032",
            "ehr_writer": "http://localhost:8033",
            "primary_care": "http://localhost:8034",
            "specialty_care": "http://localhost:8035",
            "telehealth": "http://localhost:8036",
            "home_visit": "http://localhost:8037",
            "ccm": "http://localhost:8038",
            "clinician_avatar": "http://localhost:8039",
        }
        db_urls = seed_db.get_all_agent_urls()
        for alias, expected_url in old_base_urls.items():
            assert db_urls.get(alias) == expected_url, (
                f"Mismatch for {alias}: expected {expected_url}, got {db_urls.get(alias)}"
            )


# ── Seed personas ────────────────────────────────────────────────────────


class TestSeedPersonas:
    def test_seed_personas_from_config(self, seed_db: NexusSeedDB):
        rows = seed_db._backend.execute("SELECT COUNT(*) FROM personas")
        assert rows[0][0] >= 60, f"Expected at least 60 personas, got {rows[0][0]}"


# ── Job profiles ─────────────────────────────────────────────────────────


class TestJobProfiles:
    def test_get_job_profiles(self, seed_db: NexusSeedDB):
        profiles = seed_db.get_job_profiles()
        assert len(profiles) >= 20, f"Expected at least 20 profiles, got {len(profiles)}"
        assert profiles.get("triage") == "Triage Nurse"
        assert profiles.get("pharmacy") == "Pharmacist"
        assert profiles.get("imaging") == "Radiologist"


# ── Triage rules ─────────────────────────────────────────────────────────


class TestTriageRules:
    def test_chest_pain_esi2(self, seed_db: NexusSeedDB):
        assert seed_db.evaluate_triage_rules("Severe chest pain") == "ESI-2"

    def test_shortness_of_breath_esi2(self, seed_db: NexusSeedDB):
        assert seed_db.evaluate_triage_rules("acute shortness of breath") == "ESI-2"

    def test_low_spo2_esi2(self, seed_db: NexusSeedDB):
        assert seed_db.evaluate_triage_rules("cough", {"spo2": 88}) == "ESI-2"

    def test_high_temp_esi2(self, seed_db: NexusSeedDB):
        assert seed_db.evaluate_triage_rules("headache", {"temp_c": 39.5}) == "ESI-2"

    def test_confusion_esi2(self, seed_db: NexusSeedDB):
        assert seed_db.evaluate_triage_rules("sudden confusion") == "ESI-2"

    def test_laceration_esi4(self, seed_db: NexusSeedDB):
        assert seed_db.evaluate_triage_rules("minor laceration on hand") == "ESI-4"

    def test_default_esi3(self, seed_db: NexusSeedDB):
        assert seed_db.evaluate_triage_rules("mild headache") == "ESI-3"

    def test_normal_vitals_default(self, seed_db: NexusSeedDB):
        assert seed_db.evaluate_triage_rules(
            "knee pain", {"spo2": 98, "temp_c": 36.7}
        ) == "ESI-3"


# ── Dependency graph ─────────────────────────────────────────────────────


class TestDependencyGraph:
    def test_dependency_graph_roundtrip(self, seed_db: NexusSeedDB):
        graph = seed_db.get_dependency_graph()
        assert "triage" in graph
        assert "diagnosis" in graph.get("triage", [])
        assert "clinician_avatar" in graph.get("triage", [])

    def test_discharge_depends_on_followup(self, seed_db: NexusSeedDB):
        graph = seed_db.get_dependency_graph()
        assert "followup" in graph.get("discharge", [])


# ── Scenarios ────────────────────────────────────────────────────────────


class TestScenarios:
    def test_seed_scenarios(self, seed_db: NexusSeedDB):
        catalog = seed_db.get_scenario_catalog()
        assert len(catalog) >= 5, f"Expected at least 5 scenarios, got {len(catalog)}"

    def test_get_scenario_by_name(self, seed_db: NexusSeedDB):
        catalog = seed_db.get_scenario_catalog()
        if catalog:
            name = catalog[0]["name"]
            scenario = seed_db.get_scenario(name)
            assert scenario is not None
            assert scenario["name"] == name
            assert "journey_steps" in scenario

    def test_get_scenario_not_found(self, seed_db: NexusSeedDB):
        assert seed_db.get_scenario("nonexistent_scenario_xyz") is None


# ── Idempotency ──────────────────────────────────────────────────────────


def test_seed_all_idempotent(tmp_path: Path):
    db_path = str(tmp_path / "idempotent_test.sqlite3")
    db = NexusSeedDB(path=db_path)
    counts1 = db.seed_all()
    counts2 = db.seed_all()
    # Should not error and produce the same counts
    assert counts1 == counts2
    db.close()
