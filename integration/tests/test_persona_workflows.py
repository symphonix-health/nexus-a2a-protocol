"""
Integration tests for Capability 6: Persona-Adaptive Workflows.

Tests the unified PersonaRegistry API endpoints against live GHARRA instances,
validating persona lookup, country-aware framework selection, category filtering,
avatar key generation, and persona configuration merging.

Sprint 5 -- Capability 6 gate.
"""

from __future__ import annotations

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}{path}"


# ---------------------------------------------------------------------------
# Test: Registry Summary
# ---------------------------------------------------------------------------


class TestRegistrySummary:
    """Validate registry summary statistics."""

    def test_summary_returns_total_count(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/personas/summary"), timeout=10.0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_personas"] >= 50, f"Expected 50+ personas, got {data['total_personas']}"

    def test_summary_has_categories(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/personas/summary"), timeout=10.0)
        data = resp.json()
        cats = data["categories"]
        assert "clinical" in cats
        assert "nursing" in cats
        assert "governance" in cats
        assert "engineering" in cats

    def test_summary_has_jurisdictions(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/personas/summary"), timeout=10.0)
        data = resp.json()
        assert data["jurisdictions_supported"] >= 12

    def test_summary_has_workflow_frameworks(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/personas/summary"), timeout=10.0)
        data = resp.json()
        fws = data["workflow_frameworks"]
        assert "soap" in fws
        assert "isbar" in fws
        assert "sbar" in fws
        assert "who-surgical-checklist" in fws


# ---------------------------------------------------------------------------
# Test: Persona Listing and Filtering
# ---------------------------------------------------------------------------


class TestPersonaListing:
    """Validate persona listing with category filters."""

    def test_list_all_personas(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/personas"), timeout=10.0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 50

    def test_list_clinical_personas(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas"),
            params={"category": "clinical"},
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["category"] == "clinical"
        assert data["count"] >= 8
        for p in data["personas"]:
            assert p["category"] == "clinical"

    def test_list_nursing_personas(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas"),
            params={"category": "nursing"},
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 5
        for p in data["personas"]:
            assert p["category"] == "nursing"

    def test_list_governance_personas(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas"),
            params={"category": "governance"},
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 3

    def test_list_with_pagination(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas"),
            params={"limit": 5, "offset": 0},
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] <= 5

    def test_empty_category_returns_zero(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas"),
            params={"category": "nonexistent_category"},
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0


# ---------------------------------------------------------------------------
# Test: Single Persona Lookup
# ---------------------------------------------------------------------------


class TestPersonaLookup:
    """Validate individual persona retrieval."""

    def test_get_doctor(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/personas/doctor"), timeout=10.0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "doctor"
        assert data["category"] == "clinical"
        assert data["tone"]  # Non-empty tone
        assert len(data["capabilities"]) > 0

    def test_get_nurse(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/personas/nurse"), timeout=10.0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "nurse"
        assert data["category"] == "nursing"

    def test_get_pharmacist(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/personas/pharmacist"), timeout=10.0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "pharmacist"
        assert data["category"] == "pharmacy"

    def test_get_dpo(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/personas/dpo"), timeout=10.0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["category"] == "governance"

    def test_get_ai_engineer(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/personas/ai_engineer"), timeout=10.0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["category"] == "ai_data"

    def test_get_nonexistent_returns_404(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/nonexistent_persona_xyz"),
            timeout=10.0,
        )
        assert resp.status_code == 404

    def test_persona_has_allowed_purposes(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/personas/doctor"), timeout=10.0)
        data = resp.json()
        assert "treatment" in data["allowed_purposes"]


# ---------------------------------------------------------------------------
# Test: Country-Aware Framework Selection
# ---------------------------------------------------------------------------


class TestFrameworkSelection:
    """Validate clinical workflow framework selection per persona + jurisdiction."""

    def test_ie_doctor_gets_isbar(self, gharra_url: str) -> None:
        """Ireland defaults to ISBAR for clinical personas without overrides."""
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/doctor/framework/IE"),
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["jurisdiction"] == "IE"
        # Doctor may have a persona-specific override or fall back to IE default (ISBAR)
        assert data["framework"] in ("soap", "isbar")

    def test_gb_nurse_gets_sbar(self, gharra_url: str) -> None:
        """GB defaults to SBAR."""
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/nurse/framework/GB"),
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["jurisdiction"] == "GB"
        # Nurse may have persona-specific override (i-pass) or GB default (sbar)
        assert data["framework"] in ("sbar", "i-pass")

    def test_us_doctor_gets_soap(self, gharra_url: str) -> None:
        """US defaults to SOAP."""
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/doctor/framework/US"),
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["jurisdiction"] == "US"
        assert data["framework"] in ("soap",)

    def test_surgeon_gets_who_checklist(self, gharra_url: str) -> None:
        """Surgeon has persona-specific WHO surgical checklist override."""
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/surgeon/framework/US"),
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["framework"] == "who-surgical-checklist"

    def test_unknown_jurisdiction_gets_soap_default(self, gharra_url: str) -> None:
        """Unknown jurisdiction falls back to SOAP global default."""
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/doctor/framework/ZZ"),
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["framework"] == "soap"

    def test_nonexistent_persona_framework_404(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/nonexistent/framework/IE"),
            timeout=10.0,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Avatar Key Generation
# ---------------------------------------------------------------------------


class TestAvatarKeys:
    """Validate country-aware avatar key generation."""

    def test_ie_doctor_avatar(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/doctor/avatar/IE"),
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["persona_key"] == "doctor"
        assert data["jurisdiction"] == "IE"
        assert "doctor" in data["avatar_key"]

    def test_gb_nurse_avatar_uses_nhs_style(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/nurse/avatar/GB"),
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "nhs" in data["avatar_key"].lower()

    def test_us_doctor_avatar_uses_american_style(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/doctor/avatar/US"),
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "american" in data["avatar_key"].lower()

    def test_unknown_jurisdiction_uses_international(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/doctor/avatar/ZZ"),
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "international" in data["avatar_key"].lower()

    def test_nonexistent_persona_avatar_404(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/nonexistent/avatar/IE"),
            timeout=10.0,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Persona Config Merging
# ---------------------------------------------------------------------------


class TestPersonaConfig:
    """Validate persona config merged with jurisdiction settings."""

    def test_ie_doctor_config(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/doctor/config/IE"),
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "doctor"
        assert data["jurisdiction"] == "IE"
        assert data["language"] == "en-IE"
        assert data["consent_model"] == "opt-in"
        assert data["regulatory_body"] == "HIQA"
        assert data["early_warning_score"] == "news2"
        assert data["workflow_framework"]  # Non-empty

    def test_us_nurse_config(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/nurse/config/US"),
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["jurisdiction"] == "US"
        assert data["language"] == "en-US"
        assert data["early_warning_score"] == "mews"
        assert data["regulatory_body"] == "CMS"

    def test_de_pharmacist_config(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/pharmacist/config/DE"),
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["jurisdiction"] == "DE"
        assert data["language"] == "de-DE"

    def test_jp_config(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/doctor/config/JP"),
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["jurisdiction"] == "JP"
        assert data["language"] == "ja-JP"

    def test_config_includes_capabilities(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/doctor/config/IE"),
            timeout=10.0,
        )
        data = resp.json()
        assert len(data["capabilities"]) > 0

    def test_config_includes_avatar_key(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/doctor/config/GB"),
            timeout=10.0,
        )
        data = resp.json()
        assert data["avatar_key"]  # Non-empty

    def test_nonexistent_persona_config_404(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/nonexistent/config/IE"),
            timeout=10.0,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Search
# ---------------------------------------------------------------------------


class TestPersonaSearch:
    """Validate persona search functionality."""

    def test_search_by_title(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/search"),
            params={"q": "doctor"},
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        keys = [p["key"] for p in data["personas"]]
        assert "doctor" in keys

    def test_search_by_summary_keyword(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/search"),
            params={"q": "surgical"},
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1

    def test_search_no_results(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/search"),
            params={"q": "xyznonexistent999"},
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    def test_search_nurse(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/personas/search"),
            params={"q": "nurse"},
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 2  # nurse + public_health_nurse at minimum


# ---------------------------------------------------------------------------
# Test: Categories and Frameworks Endpoints
# ---------------------------------------------------------------------------


class TestMetadataEndpoints:
    """Validate categories, frameworks, and jurisdictions listing."""

    def test_list_categories(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/personas/categories"), timeout=10.0)
        assert resp.status_code == 200
        data = resp.json()
        cats = data["categories"]
        assert "clinical" in cats
        assert "nursing" in cats
        assert "pharmacy" in cats
        assert "governance" in cats
        assert "engineering" in cats

    def test_list_frameworks(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/personas/frameworks"), timeout=10.0)
        assert resp.status_code == 200
        data = resp.json()
        fws = data["frameworks"]
        assert len(fws) >= 10
        assert "soap" in fws
        assert "isbar" in fws
        assert "who-surgical-checklist" in fws

    def test_list_jurisdictions(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/personas/jurisdictions"), timeout=10.0)
        assert resp.status_code == 200
        data = resp.json()
        jurisdictions = data["jurisdictions"]
        assert len(jurisdictions) >= 12
        codes = [j["code"] for j in jurisdictions]
        assert "IE" in codes
        assert "GB" in codes
        assert "US" in codes
        assert "DE" in codes
        assert "JP" in codes

    def test_jurisdiction_has_full_config(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/personas/jurisdictions"), timeout=10.0)
        data = resp.json()
        ie = next(j for j in data["jurisdictions"] if j["code"] == "IE")
        assert ie["name"] == "Ireland"
        assert ie["region"] == "EU"
        assert ie["language"] == "en-IE"
        assert ie["default_framework"] == "isbar"
        assert ie["consent_model"] == "opt-in"
        assert ie["regulatory_body"] == "HIQA"


# ---------------------------------------------------------------------------
# Test: Cross-Registry Persona Consistency
# ---------------------------------------------------------------------------


class TestCrossRegistryPersonas:
    """Validate persona API is available on all GHARRA instances."""

    def test_gb_sovereign_has_personas(self, gharra_gb_url: str) -> None:
        resp = httpx.get(_url(gharra_gb_url, "/v1/personas/summary"), timeout=10.0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_personas"] >= 50

    def test_us_sovereign_has_personas(self, gharra_us_url: str) -> None:
        resp = httpx.get(_url(gharra_us_url, "/v1/personas/summary"), timeout=10.0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_personas"] >= 50

    def test_all_registries_same_count(
        self, gharra_url: str, gharra_gb_url: str, gharra_us_url: str,
    ) -> None:
        """All GHARRA instances share the same persona registry."""
        counts = []
        for url in (gharra_url, gharra_gb_url, gharra_us_url):
            resp = httpx.get(_url(url, "/v1/personas/summary"), timeout=10.0)
            assert resp.status_code == 200
            counts.append(resp.json()["total_personas"])
        assert counts[0] == counts[1] == counts[2]

    def test_gb_sovereign_uses_sbar_default(self, gharra_gb_url: str) -> None:
        resp = httpx.get(
            _url(gharra_gb_url, "/v1/personas/nurse/framework/GB"),
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Nurse-specific override or GB default
        assert data["framework"] in ("sbar", "i-pass")

    def test_us_sovereign_uses_soap_default(self, gharra_us_url: str) -> None:
        resp = httpx.get(
            _url(gharra_us_url, "/v1/personas/doctor/framework/US"),
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["framework"] == "soap"
