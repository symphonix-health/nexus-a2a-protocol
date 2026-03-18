"""L5 Unit Tests — Pathway repository loading and querying."""

import pytest
from clinical_pathways.loader import load_pathways
from clinical_pathways.repository import PathwayRepository


class TestPathwayRepository:
    def test_load_all_pathways(self, pathway_repo):
        assert pathway_repo.count >= 4, f"Expected at least 4 pathways, got {pathway_repo.count}"

    def test_get_heart_failure(self, pathway_repo):
        p = pathway_repo.get("nice-ng106-heart-failure")
        assert p is not None
        assert p.title == "Chronic Heart Failure in Adults: Diagnosis and Management"
        assert p.source_authority == "NICE"
        assert p.country == "GB"

    def test_get_copd(self, pathway_repo):
        p = pathway_repo.get("nice-ng115-copd")
        assert p is not None
        assert "Obstructive Pulmonary" in p.title or "COPD" in p.description

    def test_get_diabetes(self, pathway_repo):
        p = pathway_repo.get("nice-ng28-diabetes-type2")
        assert p is not None
        assert "Type 2 Diabetes" in p.title

    def test_get_sepsis(self, pathway_repo):
        p = pathway_repo.get("nice-ng51-sepsis")
        assert p is not None
        assert "Sepsis" in p.title

    def test_get_maternal(self, pathway_repo):
        p = pathway_repo.get("who-maternal-anc")
        assert p is not None
        assert p.source_authority == "WHO"

    def test_get_nonexistent(self, pathway_repo):
        assert pathway_repo.get("nonexistent-pathway") is None

    def test_list_active_gb(self, pathway_repo):
        gb = pathway_repo.list_active(country="GB")
        assert len(gb) >= 4

    def test_list_active_int(self, pathway_repo):
        intl = pathway_repo.list_active(country="INT")
        assert len(intl) >= 1

    def test_list_by_authority_nice(self, pathway_repo):
        nice = pathway_repo.list_by_authority("NICE")
        assert len(nice) >= 4

    def test_list_by_authority_who(self, pathway_repo):
        who = pathway_repo.list_by_authority("WHO")
        assert len(who) >= 1

    def test_search_heart(self, pathway_repo):
        results = pathway_repo.search("heart")
        assert len(results) >= 1
        assert any("heart" in r.title.lower() for r in results)

    def test_search_diabetes(self, pathway_repo):
        results = pathway_repo.search("diabetes")
        assert len(results) >= 1

    def test_search_no_results(self, pathway_repo):
        results = pathway_repo.search("xyznonexistent")
        assert len(results) == 0

    def test_all_ids(self, pathway_repo):
        ids = pathway_repo.all_ids()
        assert "nice-ng106-heart-failure" in ids
        assert "nice-ng51-sepsis" in ids

    def test_pathway_has_nodes(self, pathway_repo):
        for pid in pathway_repo.all_ids():
            p = pathway_repo.get(pid)
            assert p is not None
            assert len(p.nodes) > 0, f"Pathway {pid} has no nodes"

    def test_pathway_has_entry_node(self, pathway_repo):
        for pid in pathway_repo.all_ids():
            p = pathway_repo.get(pid)
            assert p.entry_node() is not None, f"Pathway {pid} has no entry node"

    def test_pathway_has_exit_node(self, pathway_repo):
        for pid in pathway_repo.all_ids():
            p = pathway_repo.get(pid)
            assert len(p.exit_nodes()) > 0, f"Pathway {pid} has no exit nodes"
