from __future__ import annotations

import pytest

from nexus_a2a_protocol import ProtocolValidationError, make_error, make_request, validate_envelope


def test_make_request_and_validate() -> None:
    payload = make_request("tasks/send", {"task": {"id": "abc"}}, request_id="1")
    assert payload["jsonrpc"] == "2.0"
    assert validate_envelope(payload)["method"] == "tasks/send"


def test_make_request_rejects_unknown_method() -> None:
    with pytest.raises(ProtocolValidationError):
        make_request("tasks/unknown", {}, request_id="1")


def test_validate_envelope_rejects_invalid_payload() -> None:
    with pytest.raises(ProtocolValidationError):
        validate_envelope({"jsonrpc": "1.0", "id": "1"})


def test_make_error_shape() -> None:
    payload = make_error("1", -32600, "Invalid Request")
    assert payload["error"]["code"] == -32600
    assert payload["error"]["message"] == "Invalid Request"
