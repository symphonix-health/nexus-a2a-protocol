"""L4 Contract Tests — API endpoints."""

import pytest
from fastapi.testclient import TestClient
from clinical_pathways.api.main import app


@pytest.fixture
def client():
    # Trigger startup to load pathways
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestPathwayEndpoints:
    def test_list_pathways(self, client):
        response = client.get("/v1/pathways")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 4
        assert len(data["pathways"]) >= 4

    def test_list_pathways_by_country(self, client):
        response = client.get("/v1/pathways?country=GB")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 4

    def test_get_pathway(self, client):
        response = client.get("/v1/pathways/nice-ng106-heart-failure")
        assert response.status_code == 200
        data = response.json()
        assert data["pathway_id"] == "nice-ng106-heart-failure"
        assert data["source_authority"] == "NICE"

    def test_get_pathway_not_found(self, client):
        response = client.get("/v1/pathways/nonexistent")
        assert response.status_code == 404

    def test_search_pathways(self, client):
        response = client.get("/v1/pathways/search/heart")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1


class TestPersonaliseEndpoint:
    def test_personalise_healthy_patient(self, client):
        response = client.post("/v1/pathways/personalise", json={
            "pathway_id": "nice-ng106-heart-failure",
            "patient_context": {
                "demographics": {"patient_id": "API-TEST-001", "age": 35, "gender": "female"},
                "chief_complaint": "breathlessness",
            },
        })
        assert response.status_code == 200
        data = response.json()
        assert data["pathway_id"] == "nice-ng106-heart-failure"
        assert "explainability" in data

    def test_personalise_complex_patient(self, client):
        response = client.post("/v1/pathways/personalise", json={
            "pathway_id": "nice-ng106-heart-failure",
            "patient_context": {
                "demographics": {"patient_id": "API-TEST-002", "age": 72, "gender": "male"},
                "conditions": [
                    {"code": "heart_failure"},
                    {"code": "ckd_stage_3"},
                ],
                "medications": [{"code": f"med{i}"} for i in range(10)],
                "observations": [{"code": "egfr", "value": 35.0}],
                "chief_complaint": "breathlessness",
            },
        })
        assert response.status_code == 200
        data = response.json()
        assert data["modification_count"] > 0

    def test_personalise_pathway_not_found(self, client):
        response = client.post("/v1/pathways/personalise", json={
            "pathway_id": "nonexistent",
            "patient_context": {"demographics": {"patient_id": "P1"}},
        })
        assert response.status_code == 404

    def test_personalise_consent_denied(self, client):
        response = client.post("/v1/pathways/personalise", json={
            "pathway_id": "nice-ng106-heart-failure",
            "patient_context": {
                "demographics": {"patient_id": "P1"},
                "consent_status": "denied",
            },
        })
        assert response.status_code == 403

    def test_personalise_sepsis(self, client):
        response = client.post("/v1/pathways/personalise", json={
            "pathway_id": "nice-ng51-sepsis",
            "patient_context": {
                "demographics": {"patient_id": "API-SEPSIS-001", "age": 68, "gender": "female"},
                "allergies": [{"substance": "penicillin", "reaction": "anaphylaxis", "severity": "severe"}],
                "vital_signs": {"heart_rate": 110, "systolic_bp": 85, "temperature": 38.9},
                "observations": [{"code": "lactate", "value": 3.5}],
                "chief_complaint": "fever",
            },
        })
        assert response.status_code == 200
        data = response.json()
        assert any("penicillin" in w.lower() for w in data.get("safety_warnings", []))

    def test_personalise_diabetes(self, client):
        response = client.post("/v1/pathways/personalise", json={
            "pathway_id": "nice-ng28-diabetes-type2",
            "patient_context": {
                "demographics": {"patient_id": "API-DM2-001", "age": 65, "gender": "male"},
                "conditions": [{"code": "type_2_diabetes"}, {"code": "diabetic_foot_ulcer"}],
                "medications": [{"code": "metformin"}],
                "observations": [
                    {"code": "egfr", "value": 22.0},
                    {"code": "hba1c", "value": 82.0},
                ],
            },
        })
        assert response.status_code == 200
        data = response.json()
        assert data["modification_count"] > 0
