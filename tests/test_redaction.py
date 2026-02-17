"""Tests for shared.nexus_common.redaction – PHI field-level scrubbing."""

from __future__ import annotations

from shared.nexus_common.redaction import REDACTED, redact_payload


class TestRedactPayloadBasic:
    """Core redaction behaviour."""

    def test_empty_input_returns_empty(self) -> None:
        redacted, meta = redact_payload(None)
        assert redacted == {}
        assert meta["masked_fields"] == []

    def test_empty_dict_returns_empty(self) -> None:
        redacted, meta = redact_payload({})
        assert redacted == {}
        assert meta["masked_fields"] == []

    def test_phi_keys_redacted(self) -> None:
        data = {
            "name": "Jane Doe",
            "mrn": "MRN-12345",
            "dob": "1990-01-01",
            "phone": "555-0100",
            "email": "jane@example.com",
            "ssn": "123-45-6789",
            "insurance_id": "INS-999",
        }
        redacted, meta = redact_payload(data)
        for key in data:
            assert redacted[key] == REDACTED, f"Expected {key} to be redacted"
        assert len(meta["masked_fields"]) == len(data)

    def test_safe_clinical_keys_preserved(self) -> None:
        data = {
            "age": 42,
            "gender": "female",
            "chief_complaint": "chest pain",
            "symptoms": ["cough", "fever"],
            "differential_diagnosis": ["pneumonia"],
        }
        redacted, meta = redact_payload(data)
        assert redacted == data
        assert meta["masked_fields"] == []


class TestRedactPayloadNested:
    """Nested structures and arrays."""

    def test_nested_dict_redacts_phi(self) -> None:
        data = {
            "patient": {
                "name": "John Smith",
                "age": 65,
                "address": "123 Main St",
            }
        }
        redacted, meta = redact_payload(data)
        assert redacted["patient"]["name"] == REDACTED
        assert redacted["patient"]["address"] == REDACTED
        assert redacted["patient"]["age"] == 65
        assert "patient.name" in meta["masked_fields"]
        assert "patient.address" in meta["masked_fields"]

    def test_list_of_dicts_redacted(self) -> None:
        data = {
            "contacts": [
                {"name": "Alice", "phone": "555-0001"},
                {"name": "Bob", "phone": "555-0002"},
            ]
        }
        redacted, meta = redact_payload(data)
        for contact in redacted["contacts"]:
            assert contact["name"] == REDACTED
            assert contact["phone"] == REDACTED


class TestRedactPayloadJWT:
    """JWT masking."""

    def test_jwt_token_masked(self) -> None:
        jwt = (
            "eyJhbGciOiJIUzI1NiJ9"
            ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
            ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        )
        data = {"auth_token": jwt}
        redacted, meta = redact_payload(data)
        assert redacted["auth_token"] == REDACTED
        assert any("jwt" in f for f in meta["masked_fields"])

    def test_bearer_jwt_masked(self) -> None:
        jwt = (
            "Bearer eyJhbGciOiJIUzI1NiJ9"
            ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
            ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        )
        data = {"authorization": jwt}
        redacted, meta = redact_payload(data)
        assert redacted["authorization"] == REDACTED

    def test_non_jwt_string_not_masked(self) -> None:
        data = {"note": "Patient reports feeling better today"}
        redacted, meta = redact_payload(data)
        assert redacted["note"] == data["note"]


class TestRedactPayloadMeta:
    """Redaction metadata structure."""

    def test_policy_version_included(self) -> None:
        _, meta = redact_payload({"name": "X"})
        assert meta["policy_version"] == "v1"

    def test_custom_policy_version(self) -> None:
        _, meta = redact_payload({"name": "X"}, policy="v2-beta")
        assert meta["policy_version"] == "v2-beta"

    def test_masked_fields_are_sorted_unique(self) -> None:
        data = {"name": "A", "email": "a@b.com", "phone": "555"}
        _, meta = redact_payload(data)
        fields = meta["masked_fields"]
        assert fields == sorted(set(fields))

    def test_redacted_count_matches(self) -> None:
        """Verify the redacted_count convenience — masked_fields length."""
        data = {"name": "X", "mrn": "Y", "age": 30}
        _, meta = redact_payload(data)
        # 2 PHI fields, age is safe
        assert len(meta["masked_fields"]) == 2
