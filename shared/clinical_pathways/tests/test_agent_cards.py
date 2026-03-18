"""L5 Unit Tests — Agent cards for GHARRA registration."""

import pytest
from clinical_pathways.agent_cards import (
    CONTEXT_ASSEMBLER_AGENT_CARD,
    PATHWAY_KNOWLEDGE_AGENT_CARD,
    PATHWAY_PERSONALISATION_AGENT_CARD,
    get_all_agent_cards,
)


class TestAgentCards:
    def test_all_cards_returned(self):
        cards = get_all_agent_cards()
        assert len(cards) == 3

    def test_knowledge_agent_card(self):
        card = PATHWAY_KNOWLEDGE_AGENT_CARD
        assert card["agent_id"] == "pathway-knowledge-agent"
        assert card["provider"] == "Symphonix-Health"
        assert len(card["capabilities"]) >= 1
        assert card["trust_metadata"]["audit_logging"] is True

    def test_personalisation_agent_card(self):
        card = PATHWAY_PERSONALISATION_AGENT_CARD
        assert card["agent_id"] == "pathway-personalisation-agent"
        assert len(card["capabilities"]) >= 2
        assert card["trust_metadata"]["explainability"] is True
        assert card["trust_metadata"]["clinician_in_the_loop"] is True
        assert len(card["personalisation_rules"]) >= 15

    def test_context_assembler_card(self):
        card = CONTEXT_ASSEMBLER_AGENT_CARD
        assert card["agent_id"] == "context-assembler-agent"
        assert card["trust_metadata"]["consent_checking"] is True
        assert card["trust_metadata"]["phi_redaction"] is True

    def test_all_cards_have_required_fields(self):
        for card in get_all_agent_cards():
            assert "agent_id" in card
            assert "name" in card
            assert "description" in card
            assert "capabilities" in card
            assert "interoperability" in card
            assert "trust_metadata" in card

    def test_all_cards_use_a2a_protocol(self):
        for card in get_all_agent_cards():
            assert card["interoperability"]["protocol"] == "a2a"

    def test_supported_pathways_listed(self):
        card = PATHWAY_KNOWLEDGE_AGENT_CARD
        pathways = card["supported_pathways"]
        assert "nice-ng106-heart-failure" in pathways
        assert "nice-ng51-sepsis" in pathways
        assert "who-maternal-anc" in pathways
