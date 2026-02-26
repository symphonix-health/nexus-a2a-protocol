# IAM Identity Architecture for NEXUS A2A Agents
## Agent Personas, Delegated Authority, and Autonomous Communication

**Version**: 1.0 — February 2026
**Status**: Research & Design
**Scope**: HelixCare / NEXUS Agent-to-Agent Protocol

---

## 1. Vision

The goal is to give each NEXUS agent a **verified, governable identity** — just as a human clinician has an NHS Smartcard, a hospital badge, and a role in Active Directory. Agents can then:

- Act autonomously within the bounds of their persona and RBAC policy
- Delegate work to other agents (and receive delegated work)
- Send and receive email and SMS on behalf of their clinical role
- Be audited, suspended, or re-scoped like any other identity in the organisation
- Participate in the same Conditional Access and MFA policies as human staff

This is **not** chatbot identity. It is **enterprise service identity** applied to AI agents, using standards that healthcare organisations already operate (Entra ID / Azure AD, NHS NRBAC, SMART on FHIR, HL7 RBAC).

---

## 2. Identity Provider Options

| Provider | Best For | Agent Model | Key Capability |
|----------|----------|-------------|----------------|
| **Microsoft Entra ID** (formerly Azure AD) | NHS Trusts, US health systems on M365 | App Registration + Service Principal | Managed Identity, Graph API, Conditional Access |
| **AWS IAM / Cognito** | AWS-native deployments | IAM Role + OIDC federation | STS AssumeRole, Cognito Machine Credentials |
| **Okta** | Mixed cloud environments | Machine-to-Machine (M2M) Application | OAuth 2.0 Client Credentials + Groups |
| **Ping Identity** | Large NHS / enterprise | OAuth 2.0 + FHIR SMART | SMART on FHIR backend services launch |
| **NHS Identity** (CIS2) | NHS England deployments | System-to-system identity | NHS Smartcard-equivalent for systems |

**Recommended for HelixCare**: **Microsoft Entra ID** — already used across NHS and US health systems, supports Managed Identity for zero-secret agent auth, and provides Microsoft Graph API for email/SMS/Teams.

---

## 3. Agent as Entra Service Principal

### 3.1 Registration Model

Each NEXUS agent is registered as an **Entra App Registration**, producing:
- **Application (client) ID** — unique agent identifier
- **Service Principal** — the agent's "account" in the tenant
- **Client secret or certificate** — or replaced by **Managed Identity** in Azure

```
Azure Tenant: nexus-helixcare.onmicrosoft.com
├── App Registrations
│   ├── NEXUS Triage Agent          [P004 Triage Nurse]
│   ├── NEXUS Diagnosis Agent       [P001 Consultant Physician]
│   ├── NEXUS Imaging Agent         [P005 Radiologist]
│   ├── NEXUS Pharmacy Agent        [P007 Pharmacist]
│   ├── NEXUS Bed Manager Agent     [P045 Bed Manager]
│   ├── NEXUS Discharge Agent       [P001 Consultant Physician]
│   ├── NEXUS Follow-up Scheduler   [P021 Care Coordinator]
│   ├── NEXUS Care Coordinator      [P021 Care Coordinator]
│   ├── NEXUS Clinician Avatar      [P001 Consultant Physician]
│   ├── NEXUS Consent Analyser      [P013 Caldicott Guardian]
│   ├── NEXUS Hospital Reporter     [P058 CMO]
│   └── ...
└── Security Groups
    ├── nexus-clinical-high         [triage, diagnosis, imaging, pharmacy, discharge, avatar]
    ├── nexus-clinical-medium       [bed manager, followup, care coordinator, home visit, ccm]
    ├── nexus-operations            [followup, bed manager, summariser, ehr writer]
    ├── nexus-governance            [consent analyser, hospital reporter, central surveillance]
    ├── nexus-connector             [openhie mediator, insurer agent, provider agent]
    └── nexus-intelligence          [osint agent]
```

### 3.2 App Roles (mapped from BulletTrain RBAC)

Defined in the NEXUS platform App Registration manifest, consumed by all agents:

```json
{
  "appRoles": [
    {
      "id": "...",
      "displayName": "Clinical Service — High",
      "value": "clinician_service.high",
      "description": "Full clinical read/write; prescribing and order authority",
      "allowedMemberTypes": ["Application"]
    },
    {
      "id": "...",
      "displayName": "Clinical Service — Medium",
      "value": "clinician_service.medium",
      "description": "Observation and care plan read/write; no prescribing",
      "allowedMemberTypes": ["Application"]
    },
    {
      "id": "...",
      "displayName": "Patient Service",
      "value": "patient_service",
      "description": "Demographics, scheduling, limited PHI",
      "allowedMemberTypes": ["Application"]
    },
    {
      "id": "...",
      "displayName": "Auditor",
      "value": "auditor",
      "description": "Audit and consent read; no write",
      "allowedMemberTypes": ["Application"]
    },
    {
      "id": "...",
      "displayName": "Connector",
      "value": "connector",
      "description": "Integration engine; system-level read/write",
      "allowedMemberTypes": ["Application"]
    }
  ]
}
```

### 3.3 Managed Identity (Preferred — No Secrets)

When agents run on Azure (Container Apps, AKS, App Service), use **System-Assigned Managed Identity**. The agent authenticates to Entra automatically — no secrets in environment variables.

```python
# Azure SDK pattern for NEXUS agents on Azure
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential

credential = DefaultAzureCredential()   # Uses Managed Identity in Azure; env vars locally
token = credential.get_token("https://graph.microsoft.com/.default")
```

For local development, fall back to:
```bash
export AZURE_CLIENT_ID=<app-client-id>
export AZURE_CLIENT_SECRET=<client-secret>
export AZURE_TENANT_ID=<tenant-id>
```

---

## 4. OAuth 2.0 Flows for Agent Autonomy

### 4.1 Client Credentials (Agent Acting as Itself)

For agent-to-agent RPC calls (e.g., Triage → Diagnosis), each agent acquires a token for the NEXUS platform resource using its own identity:

```
POST https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id={agent_app_id}
&client_secret={agent_secret}          # or certificate / Managed Identity
&scope=api://nexus-platform/.default
```

The resulting JWT contains the agent's **app roles** (`clinician_service.high`, etc.) and is validated by receiving agents at `/rpc` alongside the NEXUS JWT.

### 4.2 On-Behalf-Of (OBO) — Agent Delegation

When Agent A delegates to Agent B on behalf of a clinical action initiated by Agent A:

```
POST https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token

grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
&client_id={agent_b_app_id}
&client_secret={agent_b_secret}
&assertion={agent_a_token}             # Agent A's access token
&scope=api://nexus-platform/patient.read api://nexus-platform/encounter.write
&requested_token_use=on_behalf_of
```

This creates an **OBO chain** — the audit log shows: `Diagnosis Agent → [OBO] → Imaging Agent`. The maximum chain depth should be enforced (recommend max 3 hops) to prevent delegation loops.

### 4.3 SMART on FHIR Backend Services Launch

For FHIR server integration (HAPI, Azure Health Data Services, Epic, Cerner):

```
POST {fhir_server}/auth/token

grant_type=client_credentials
&client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
&client_assertion={signed_jwt_with_agent_private_key}
&scope=system/Patient.read system/Encounter.write
```

Each agent's SMART scopes are defined in `config/agent_personas.json` under `iam.smart_fhir_scopes`.

---

## 5. Persona × Agent Mapping (Summary)

| Agent | Port | Persona (UK) | Persona (USA) | Persona (Kenya) | IAM Group |
|-------|------|-------------|--------------|----------------|-----------|
| Triage Agent | 8021 | P004 Triage Nurse | P016 Registered Nurse | P028 Nursing Officer | nexus-clinical-high |
| Diagnosis Agent | 8022 | P001 Consultant Physician | P014 Attending Physician | P026 Medical Officer | nexus-clinical-high |
| Imaging Agent | 8024 | P005 Radiologist | P020 Radiology Technologist | P032 Radiographer | nexus-clinical-high |
| Pharmacy Agent | 8025 | P007 Pharmacist | P018 Pharmacist | P030 Pharmacist | nexus-clinical-high |
| Bed Manager | 8026 | P045 Bed Manager | — | — | nexus-operations |
| Discharge Agent | 8027 | P001 Consultant Physician | P043 Case Manager | P026 Medical Officer | nexus-clinical-high |
| Follow-up Scheduler | 8028 | P011 Receptionist | P021 Care Coordinator | P036 CHW | nexus-operations |
| Care Coordinator | 8029 | P066 Hospital Social Worker | P021 Care Coordinator | P036 CHW | nexus-clinical-medium |
| Clinician Avatar | 8039 | P001 Consultant Physician | P014 Attending Physician | P026 Medical Officer | nexus-clinical-high |
| Consent Analyser | 8043 | P013 Caldicott Guardian | P024 Privacy Officer | — | nexus-governance |
| Hospital Reporter | 8051 | P057 Systems Analyst | P058 CMO | P035 CHMT Analyst | nexus-governance |
| Central Surveillance | 8053 | P058 CMO | P058 CMO | P035 CHMT Analyst | nexus-governance |

Full mapping: [config/agent_personas.json](../config/agent_personas.json)
Full persona registry: [config/personas.json](../config/personas.json)

---

## 6. Delegation Model

### 6.1 Who Can Delegate to Whom

```
Patient/UI
    │
    ▼
Clinician Avatar (P001)          ← initiates consultation
    │  delegates
    ▼
Care Coordinator (P021)          ← orchestrates journey
    │  delegates         │ delegates         │ delegates
    ▼                    ▼                   ▼
Triage Agent         Diagnosis Agent     Bed Manager
(P004)               (P001)              (P045)
                          │ delegates
                          ▼
                    Imaging Agent (P005)
                    Pharmacy Agent (P007)
                    Discharge Agent (P001)
                          │ delegates
                          ▼
                    Follow-up Scheduler (P021)
```

### 6.2 Delegation Constraints

| Rule | Rationale |
|------|-----------|
| Max 3 OBO hops | Prevent unbounded token chains |
| Scopes can only narrow, not widen | Agent B cannot gain scopes Agent A doesn't have |
| Segregation of Duties enforced | e.g. Pharmacy Agent cannot delegate prescribing authority it doesn't hold |
| All delegation logged to audit trail | Full OBO chain captured in `AuditEvent` (FHIR) |
| Purpose of Use must be declared | Each token includes `purpose_of_use` claim |

### 6.3 NEXUS JWT Extension for Delegation

Extend the NEXUS JWT payload to carry delegation context:

```json
{
  "sub": "nexus-diagnosis-agent",
  "scope": "nexus:invoke",
  "persona_id": "P001",
  "persona_name": "Consultant Physician",
  "bulletrain_role": "clinician_service",
  "rbac_level": "High",
  "purpose_of_use": "Treatment",
  "data_sensitivity": "High",
  "delegated_by": "nexus-triage-agent",
  "delegation_chain": ["nexus-clinician-avatar", "nexus-care-coordinator", "nexus-triage-agent"],
  "delegation_depth": 3,
  "patient_context": "visit-uuid-xyz",
  "iat": 1708900000,
  "exp": 1708903600
}
```

---

## 7. Communication Capabilities

### 7.1 Email via Microsoft Graph API

Agents with `send_email: true` can send email using **Application permission** `Mail.Send` granted in Entra. Each agent has a mailbox (shared mailbox or distribution group inbox):

```
nexus-discharge-agent@helixcare.nhs.uk   → GP discharge summaries
nexus-followup-scheduler@helixcare.nhs.uk → appointment letters
nexus-bed-manager@helixcare.nhs.uk        → capacity reports
```

Graph API call (from `AgentIdentity.graph_api_send_mail_payload()`):
```http
POST https://graph.microsoft.com/v1.0/users/{agent_upn}/sendMail
Authorization: Bearer {agent_access_token}
Content-Type: application/json

{
  "message": {
    "subject": "Discharge Summary — Patient XYZ",
    "body": { "contentType": "HTML", "content": "..." },
    "toRecipients": [{ "emailAddress": { "address": "gp@primarycare.nhs.uk" } }]
  }
}
```

### 7.2 SMS via Azure Communication Services (ACS)

Agents with `send_sms: true` use **ACS** with an application-scoped access key. Recommended pattern: ACS **Managed Identity** authentication from the agent's Entra Service Principal.

```python
from azure.communication.sms import SmsClient
from azure.identity import DefaultAzureCredential

sms_client = SmsClient(
    endpoint="https://nexus-comms.communication.azure.com",
    credential=DefaultAzureCredential(),
)
sms_client.send(
    from_="<ACS_phone_number>",
    to=["+447700900123"],
    message="Your appointment is confirmed for tomorrow at 10am.",
    enable_delivery_report=True,
)
```

| Agent | SMS Permission | Scope |
|-------|---------------|-------|
| Pharmacy Agent | Send only | Medication ready / collection |
| Bed Manager | Send + Receive | Bed alerts to ward staff |
| Follow-up Scheduler | Send + Receive | Appointment reminders, reply-to-cancel |
| Discharge Agent | Send only | Patient discharge notification |
| CCM Agent | Send + Receive | Chronic condition check-ins |
| Home Visit Agent | Send + Receive | Visit confirmation and escalation |

### 7.3 Receive Email / SMS — Inbound Processing

Agents with `receive_email: true` subscribe to an **Event Grid** topic on their shared mailbox via **Microsoft Graph webhooks**:

```
Graph API webhook → Event Grid → Azure Function → NEXUS agent /rpc (notification method)
```

Agents with `receive_sms: true` use **ACS Event Grid** to receive inbound SMS and route to the agent's `/rpc` endpoint with method `agent/inbound_sms`.

---

## 8. Conditional Access for Agent Identities

Define Conditional Access policies scoped to NEXUS service principals:

| Policy | Applies To | Condition | Action |
|--------|-----------|-----------|--------|
| **Nexus-Clinical-High MFA** | nexus-clinical-high group | All sign-ins | Require strong auth (certificate or Managed Identity) |
| **Geo-Restrict** | All agents | Sign-in from outside NHS/Azure UK regions | Block |
| **Anomaly Detection** | All agents | Unusual volume or off-hours activity | Require HITL review + alert |
| **High Sensitivity Guard** | clinician_service.high role | Access to High sensitivity data | Require patient context claim |
| **Segregation Enforcement** | All agents | Attempting scope outside persona | Deny + audit |

For NHS deployments, align with **NHS DSPT** (Data Security and Protection Toolkit) requirements and **NIST 800-53 AC-2** (Account Management).

---

## 9. Regulatory Mapping

### 9.1 UK NHS (England)

| NEXUS Concept | NHS Equivalent |
|--------------|----------------|
| Agent Service Principal | NHS System-to-System identity (CIS2) |
| nexus-clinical-high group | NRBAC clinical practitioner roles |
| RBAC High = `clinician_service` | NRBAC Job Role Codes (JRC) for prescribers |
| Caldicott Guardian persona (P013) | Caldicott Guardian role — consent oversight |
| NHS RA Agent persona (P012) | Registration Authority — role provisioning |
| Audit expectation = Full | NHS DSP Toolkit — Audit Logging standard |

### 9.2 USA (HIPAA)

| NEXUS Concept | HIPAA Equivalent |
|--------------|-----------------|
| `purpose_of_use` claim | HIPAA Purpose of Use (45 CFR §164.506) |
| `data_sensitivity: High` | PHI — minimum necessary principle |
| OBO delegation chain | Business Associate Agreement (BAA) chain |
| Audit logging | HIPAA Security Rule §164.312(b) |
| Consent Analyser agent | Privacy Officer function |

### 9.3 Kenya (KHIS / MOH)

| NEXUS Concept | Kenya Equivalent |
|--------------|----------------|
| Personas P026–P036 | MOH Kenya cadre definitions |
| P034 Facility Data Clerk | DHIS2 / KHIS data entry role |
| P035 CHMT Analyst | County Health Management Team access |
| P059 Public Health Surveillance | IDSR (Integrated Disease Surveillance & Response) reporter |

---

## 10. Implementation Roadmap

### Phase 1 — Persona Registry (Complete)
- [x] Extract 68 personas from Excel → `config/personas.json`
- [x] Map each agent to primary/alternate personas → `config/agent_personas.json`
- [x] `shared/nexus_common/identity/` module — `PersonaRegistry`, `AgentIdentity`
- [x] Avatar agent uses registry for persona selection
- [x] New RPC method `avatar/list_personas` and REST endpoint `GET /api/identity`

### Phase 2 — Entra Integration (Next Sprint)
- [ ] Create Entra App Registration for each agent (`tools/provision_entra_agents.py`)
- [ ] Assign App Roles from BulletTrain RBAC → Entra manifest
- [ ] Create Entra Security Groups matching `iam_groups` in `agent_personas.json`
- [ ] Configure Managed Identity for Azure-hosted agents
- [ ] Store `entra_app_id` in `config/agent_personas.json`
- [ ] Extend `mint_jwt()` to embed persona claims from registry

### Phase 3 — Delegated Auth in Agent-to-Agent Calls
- [ ] Implement OBO token exchange in `shared/nexus_common/auth.py`
- [ ] Add `delegated_by` and `delegation_chain` claims to NEXUS JWT
- [ ] Enforce delegation policy in JWT verification middleware
- [ ] Add `X-Delegation-Chain` header to agent-to-agent RPC calls
- [ ] Add delegation audit events to SSE event bus

### Phase 4 — Communication Channels
- [ ] Provision shared mailboxes in Exchange Online for eligible agents
- [ ] Grant `Mail.Send` + `Mail.Read` Graph API permissions
- [ ] Implement `GraphMailClient` in `shared/nexus_common/identity/mail.py`
- [ ] Provision ACS phone numbers for SMS-eligible agents
- [ ] Implement `ACSSmSClient` in `shared/nexus_common/identity/sms.py`
- [ ] Set up Graph webhooks for inbound email routing
- [ ] Set up ACS Event Grid for inbound SMS routing

### Phase 5 — Conditional Access & Audit
- [ ] Define Conditional Access policies in Entra Admin Centre
- [ ] Wire Entra audit log → NEXUS SSE bus (via Entra diagnostic settings → Event Hub)
- [ ] Map Entra `AuditEvent` → FHIR `AuditEvent` resource
- [ ] HITL review queue for Conditional Access denied events

---

## 11. Local Development Without Entra

Until Entra is provisioned, agents continue to use the existing NEXUS JWT with the dev secret. The persona and IAM group information from the registry is embedded in the JWT:

```python
# tools/mint_agent_token.py (proposed)
from shared.nexus_common.auth import mint_jwt
from shared.nexus_common.identity import get_agent_identity

identity = get_agent_identity("diagnosis_agent")
persona = identity.primary_persona

extra_claims = persona.to_jwt_claims_dict()
extra_claims["iam_groups"] = identity.iam_groups
extra_claims["delegated_scopes"] = identity.delegated_scopes

token = mint_jwt(
    subject=f"nexus-{identity.agent_id}",
    secret=os.environ["NEXUS_JWT_SECRET"],
    extra_claims=extra_claims,
)
```

This ensures the same persona semantics are present in tokens whether using local JWT or full Entra tokens.

---

## 12. Key Files

| File | Purpose |
|------|---------|
| [config/personas.json](../config/personas.json) | 68 persona definitions (from Excel) |
| [config/agent_personas.json](../config/agent_personas.json) | Agent → persona mapping + IAM groups + communication permissions |
| [shared/nexus_common/identity/persona_registry.py](../shared/nexus_common/identity/persona_registry.py) | `PersonaRegistry` class — load, filter, select personas |
| [shared/nexus_common/identity/agent_identity.py](../shared/nexus_common/identity/agent_identity.py) | `AgentIdentity` — persona selection, Graph/ACS payload builders |
| [avatar/BulletTrain_personas_rbac_config_70plus_v2.xlsx](../avatar/BulletTrain_personas_rbac_config_70plus_v2.xlsx) | Source spreadsheet |

---

## 13. References

- [Microsoft Entra Workload Identities](https://learn.microsoft.com/en-us/entra/workload-id/workload-identities-overview)
- [Microsoft Graph API — Send Mail](https://learn.microsoft.com/en-us/graph/api/user-sendmail)
- [Azure Communication Services — SMS](https://learn.microsoft.com/en-us/azure/communication-services/quickstarts/sms/send)
- [OAuth 2.0 On-Behalf-Of Flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow)
- [SMART on FHIR Backend Services](https://hl7.org/fhir/smart-app-launch/backend-services.html)
- [NHS NRBAC](https://digital.nhs.uk/services/registration-authorities-and-smartcards/nhs-role-based-access-control)
- [NHS CIS2 System Identity](https://digital.nhs.uk/developer/guides-and-documentation/security-and-authorisation/nhs-cis2-im1)
- [HIPAA Minimum Necessary Standard](https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/minimum-necessary-standard/index.html)
