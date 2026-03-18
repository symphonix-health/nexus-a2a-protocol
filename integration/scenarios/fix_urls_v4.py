"""Final pass -- fix last 4 failures."""
import json

with open("scenarios/risk_mitigation_regression_matrix.json") as f:
    data = json.load(f)

lookup = {s["use_case_id"]: s for s in data}

# RMR-00045: anchor-report takes query params, not POST body
s = lookup["RMR-00045"]
s["input_payload"]["method"] = "POST"
s["input_payload"]["url"] = "/v1/admin/ledger/anchor-report?report_hash=sha256:abc123def456&report_type=conformance"
s["input_payload"].pop("body", None)
s["expected_result"] = {"contains": ["anchored"]}

# RMR-00055: The agent gets registered but may 409 on re-registration.
# The erasure works when agent exists. The 422 means registration failed.
# Fix: ensure the test runner registers with correct format.
# Actually the probe shows 200 after registration. The issue is test execution order.
# The _ensure_erasure_agent registers it, but the next erasure call succeeds.
# Problem: 422 means the erasure endpoint itself rejected. Let me check.
# Actually the probe shows erasure returns 200. The 422 in test is from registration,
# which then fails the erasure. The agent_id must not already exist.
# Use unique agent IDs per test run to avoid conflicts.
import uuid
s = lookup["RMR-00055"]
s["input_payload"]["body"]["agent_id"] = "gharra://ie/agents/erasure-regr-" + uuid.uuid4().hex[:8]
s = lookup["RMR-00056"]
s["input_payload"]["body"]["agent_id"] = "gharra://ie/agents/erasure-regr-" + uuid.uuid4().hex[:8]

# RMR-00065: key is total_active_mitigations
s = lookup["RMR-00065"]
s["expected_result"] = {"contains": ["total_active_mitigations"]}

# RMR-00075: federation/updates needs source_registry_id and proper payload
s = lookup["RMR-00075"]
s["input_payload"]["body"] = {
    "type": "agent.registered",
    "source_registry_id": "gharra://gb",
    "agent_id": "gharra://gb/agents/fed-regression-test",
    "display_name": "Federation regression test agent",
    "jurisdiction": "GB",
}
s["auth_mode"] = "idempotency_key"

with open("scenarios/risk_mitigation_regression_matrix.json", "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("Applied v4 final fixes")
