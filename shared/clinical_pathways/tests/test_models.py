"""L5 Unit Tests — Pathway definition models."""

import pytest
from clinical_pathways.models import (
    Activity,
    ActivityCategory,
    ComparisonOperator,
    Criterion,
    CriteriaGroup,
    DecisionBranch,
    NodeType,
    PathwayDefinition,
    PathwayNode,
    PathwayStatus,
    UrgencyLevel,
)


class TestCriterion:
    def test_create_criterion(self):
        c = Criterion(field="demographics.age", operator=ComparisonOperator.GE, value=18)
        assert c.field == "demographics.age"
        assert c.operator == ComparisonOperator.GE
        assert c.value == 18

    def test_criterion_with_description(self):
        c = Criterion(field="conditions[].code", operator=ComparisonOperator.CONTAINS, value="ckd", description="Has CKD")
        assert c.description == "Has CKD"


class TestActivity:
    def test_create_activity(self):
        a = Activity(activity_id="test-1", name="Blood Test", category=ActivityCategory.DIAGNOSTIC)
        assert a.activity_id == "test-1"
        assert a.category == ActivityCategory.DIAGNOSTIC
        assert a.urgency == UrgencyLevel.ROUTINE

    def test_activity_with_contraindications(self):
        ci = Criterion(field="allergies[].substance", operator=ComparisonOperator.CONTAINS, value="penicillin")
        a = Activity(activity_id="test-2", name="Amoxicillin", category=ActivityCategory.TREATMENT, contraindications=[ci])
        assert len(a.contraindications) == 1


class TestPathwayNode:
    def test_entry_node(self):
        n = PathwayNode(node_id="entry", node_type=NodeType.ENTRY, name="Entry", default_next="next")
        assert n.node_type == NodeType.ENTRY
        assert n.default_next == "next"

    def test_decision_node_with_branches(self):
        branch = DecisionBranch(branch_id="b1", target_node_id="action-1", description="Branch 1")
        n = PathwayNode(node_id="decision-1", node_type=NodeType.DECISION, name="Decision", branches=[branch])
        assert len(n.branches) == 1
        assert n.branches[0].target_node_id == "action-1"


class TestPathwayDefinition:
    def test_create_minimal_pathway(self):
        entry = PathwayNode(node_id="entry", node_type=NodeType.ENTRY, name="Entry", default_next="exit")
        exit_node = PathwayNode(node_id="exit", node_type=NodeType.EXIT, name="Exit")
        pd = PathwayDefinition(
            pathway_id="test-pathway",
            title="Test Pathway",
            version="1.0",
            source_authority="TEST",
            nodes=[entry, exit_node],
        )
        assert pd.pathway_id == "test-pathway"
        assert pd.status == PathwayStatus.ACTIVE

    def test_get_node(self):
        entry = PathwayNode(node_id="entry", node_type=NodeType.ENTRY, name="Entry")
        pd = PathwayDefinition(pathway_id="t", title="T", version="1.0", source_authority="T", nodes=[entry])
        assert pd.get_node("entry") is not None
        assert pd.get_node("nonexistent") is None

    def test_entry_node_lookup(self):
        entry = PathwayNode(node_id="entry", node_type=NodeType.ENTRY, name="Entry")
        action = PathwayNode(node_id="action", node_type=NodeType.ACTION, name="Action")
        pd = PathwayDefinition(pathway_id="t", title="T", version="1.0", source_authority="T", nodes=[entry, action])
        assert pd.entry_node().node_id == "entry"

    def test_exit_nodes(self):
        entry = PathwayNode(node_id="entry", node_type=NodeType.ENTRY, name="Entry")
        exit1 = PathwayNode(node_id="exit1", node_type=NodeType.EXIT, name="Exit 1")
        exit2 = PathwayNode(node_id="exit2", node_type=NodeType.EXIT, name="Exit 2")
        pd = PathwayDefinition(pathway_id="t", title="T", version="1.0", source_authority="T", nodes=[entry, exit1, exit2])
        assert len(pd.exit_nodes()) == 2

    def test_node_index(self):
        entry = PathwayNode(node_id="entry", node_type=NodeType.ENTRY, name="Entry")
        pd = PathwayDefinition(pathway_id="t", title="T", version="1.0", source_authority="T", nodes=[entry])
        assert "entry" in pd.node_index
