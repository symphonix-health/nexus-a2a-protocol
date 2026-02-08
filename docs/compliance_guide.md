# Nexus A2A: Regulatory Compliance Guide

**Scope**: EU AI Act, HIPAA (USA), GDPR (Europe)  
**Audience**: Data Protection Officers (DPO), System Architects, Compliance leads.

---

## I. The Shared Responsibility Model

Compliance is a shared responsibility between the **Protocol** (the rigorous standards we define) and the **Implementation** (how you deploy it).

| Layer | Responsibility | Nexus Provision |
| :--- | :--- | :--- |
| **Protocol** | Secure Transport, Identity, Schema Validation | TLS 1.3, DID:Web, JSON-RPC Validation |
| **Application** | Logic, Decision Making, Privacy Filters | **Modular Add-ons** (Audit, HITL, PII Redaction) |
| **Infrastructure** | Encryption at Rest, Access Logs | **Implementer Responsibility** (FDE, SIEM) |

---

## II. Module 1: High-Risk AI Strategy (EU AI Act)

**Risk**: Autonomous Triage Agents (`ed-triage`) are likely **Class IIa Medical Device Software**.
**Requirement**: Article 14 - "Human Oversight".

### The Solution: "HITL Interceptor" Pattern
You MUST NOT allow an AI agent to execute a clinical action (e.g., admitting a patient) directly. You must configure a **Human-in-the-Loop (HITL)** interceptor.

**Configuration:**
Instead of Triage Agent $\to$ Diagnosis Agent, configure:
`Triage Agent` $\to$ **`HITL UI Agent`** $\to$ `Diagnosis Agent`

This agent acts as a "Circuit Breaker," holding the task in a `PAUSED` state until a human signs it using a UI.

---

## III. Module 2: Enhanced Privacy (GDPR)

**Risk**: "Data Minimization" (Article 5c). Sending full patient history to an LLM.

### The Solution: PII Redaction Middleware
Nexus agents support a pluggable middleware layer. You should enable `PII_REDACTION` for any agent communicating with public LLMs.

*   **Filter**: Regex/NER to strip Names, SSNs, and Phone Numbers.
*   **Result**: The LLM sees: *"Patient [REDACTED] presents with..."*

---

## IV. Module 3: Security Hardening (HIPAA)

**Risk**: "Security Rule" (Access Control & Encryption).

### 1. Audit Log Sidecar (Add-on)
Typical Docker logs are insufficient. Deploy an **Audit Sidecar** container alongside your Agent.
*   **Function**: Subscribes to the internal event bus.
*   **Output**: Ships structured JSON logs (`{who, what, when, did}`) to an immutable SIEM (e.g., Splunk).

### 2. Encryption at Rest (Adapter)
The reference implementations use `PlaintextStorage`. For production, you must swap the storage adapter.
*   **Code Change**: Inject `EncryptedSqliteAdapter` (using SQLCipher) into the agent's Main method.

---

## V. Compliance Verification Matrix (Template)

Adopters should use this JSON template to define and test their specific compliance add-ons.

**File**: `tests/compliance/my_hospital_compliance.json`

```json
{
  "id": "UC-COMP-HITL-01",
  "name": "Audit Log Verification for HITL Interception",
  "description": "Verifies that a High-Risk request triggers a 'paused' state.",
  "type": "compliance",
  "tags": ["HITL", "Audit", "EU-AI-Act"],
  "inputs": {
    "payload": {
      "jsonrpc": "2.0",
      "method": "medical_request/authorize",
      "params": {
        "risk_score": 95,
        "action": "prescribe_opioid"
      }
    }
  },
  "expectations": {
    "http_status": 202,
    "response_state": "paused",
    "required_events": [
      {
        "topic": "audit.log.entry",
        "content_match": { "event_type": "INTERCEPTION", "reason": "HIGH_RISK" }
      },
      {
        "topic": "nexus.task.status",
        "content_match": { "status": "waiting_for_approval" }
      }
    ]
  }
}
```

### How to Run
Use the generic compliance runner (roadmap feature) to validate your add-ons against this matrix:
```bash
NEXUS_COMPLIANCE_MATRIX=./metrics/my_matrix.json pytest tests/test_compliance_generic.py
```
