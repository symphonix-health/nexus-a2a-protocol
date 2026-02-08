# White Paper: Building an Autonomous Digital Hospital with Nexus A2A

**Version:** 1.0  
**Date:** February 8, 2026  
**Prepared for:** Nexus A2A adopters (hospital systems, ministries of health, digital health architects, compliance leaders)

## Executive Summary

This white paper presents a practical blueprint for using `nexus-a2a` to build an autonomous digital hospital: a hospital where software agents execute high-volume operational and clinical workflows under explicit policy, safety, and human-oversight controls.

The core idea is to use agent interoperability as the hospital control plane. Rather than building one large monolithic platform, the hospital composes specialized agents (triage, diagnosis support, consent verification, documentation, surveillance, scheduling, discharge, billing) that communicate through standardized task contracts and event streams.

`nexus-a2a` already demonstrates critical building blocks for this model:

1. JSON-RPC task exchange and strict envelope validation.
2. JWT-based service-to-service authorization.
3. Multi-agent orchestration across healthcare use cases (`ed-triage`, `telemed-scribe`, `consent-verification`, `public-health-surveillance`).
4. Real-time workflow streaming (SSE/WebSocket).
5. Compliance-oriented testing patterns and traceability hooks.

This paper combines repository evidence with current (as of February 8, 2026) regulatory, standards, and policy guidance across the U.S., EU, and international frameworks.

## 1. Why an Autonomous Digital Hospital Now

Hospitals face simultaneous pressure on throughput, labor, quality, and compliance. Point automation (one AI model per department) creates fragmented risk and integration debt. The autonomous digital hospital model addresses this by treating orchestration, governance, and interoperability as first-class capabilities.

Key external drivers:

1. **Interoperability mandates are maturing.** U.S. ONC HTI rules and CMS API requirements continue to raise expectations for computable, standards-based exchange and transparency.
2. **AI regulation is becoming operational.** EU AI Act phased applicability is underway, and U.S. regulators have advanced concrete AI/medical-device and security governance expectations.
3. **Cybersecurity is now clinical risk.** HHS cybersecurity performance goals and NIST frameworks push toward measurable controls, not generic "best effort."
4. **Networked trust is scaling.** TEFCA participation has materially expanded, making federated exchange increasingly practical for production health systems.

## 2. Nexus A2A as the Hospital Agent Mesh

### 2.1 Design principle

Use `nexus-a2a` as a **task-and-policy mesh**, not merely an API gateway:

1. Every action is a task with sender, recipient, method, and policy context.
2. Each task emits lifecycle events for traceability and supervision.
3. Each high-risk transition can require explicit human or policy approval.
4. Each agent remains independently deployable and replaceable.

### 2.2 Evidence from current repository

Current repo capabilities already align with this approach:

1. **Protocol and auth core**
   - `shared/nexus_common/jsonrpc.py`
   - `shared/nexus_common/auth.py`
   - `shared/nexus_common/http_client.py`
   - `shared/nexus_common/sse.py`
2. **Healthcare workflow compositions**
   - ED Triage: `demos/ed-triage/`
   - Telemed Scribe: `demos/telemed-scribe/`
   - Consent Verification: `demos/consent-verification/`
   - Public Health Surveillance: `demos/public-health-surveillance/`
3. **Governance/testing artifacts**
   - Traceability: `docs/traceability-matrix.md`
   - Compliance guidance: `docs/compliance_guide.md`
   - Conformance report: `docs/conformance-report.json`

### 2.3 Current maturity snapshot

The latest conformance artifact (`docs/conformance-report.json`, generated February 8, 2026) reports:

1. `total: 140`
2. `passed: 55`
3. `failed: 55`
4. `skipped: 30`

Interpretation: the platform is a strong reference baseline but not production-ready without remediation of failing scenarios and formal hardening.

## 3. Target Architecture for an Autonomous Digital Hospital

### 3.1 Layered reference model

1. **Experience Layer**
   - Clinician console, command center, patient channels, HITL review UI.
2. **Clinical Workflow Agent Layer**
   - Triage, diagnosis support, scribe, consent, case management, discharge, claims.
3. **Policy and Safety Layer**
   - Risk scoring, policy-as-code, HITL interception, model routing, override controls.
4. **Interoperability Layer**
   - FHIR/SMART adapters, payer APIs, TEFCA connector, external provider connectors.
5. **Identity and Trust Layer**
   - Agent identity, token scopes, mTLS, DID/VC roadmap, key lifecycle.
6. **Data and Telemetry Layer**
   - Event bus, audit logs, provenance ledger, quality metrics, drift and incident signals.
7. **Infrastructure Layer**
   - Container platform, zero-trust networking, secrets management, SRE observability.

### 3.2 Control-loop model (hospital autonomy cycle)

Each autonomous workflow should run a deterministic loop:

1. **Sense:** acquire task context from EHR, devices, forms, or external feeds.
2. **Interpret:** agent creates structured inference or recommendation.
3. **Decide:** policy engine determines auto-execute vs. escalate.
4. **Act:** execute allowed operation (write note, place referral, trigger outreach).
5. **Verify:** check post-conditions and safety constraints.
6. **Learn:** feed outcomes into QA, drift detection, and governance dashboards.

### 3.3 Example operational topology

```text
EHR/FHIR  --->  Intake Agent  --->  Triage Agent  --->  Diagnosis Support Agent
   |                |                 |                    |
   |                |                 v                    v
   |                +------------> HITL Interceptor <--- Policy Engine
   |                                      |
   v                                      v
Consent Agent ----------------------> Decision + Audit Trail
   |
   v
Care Execution Agents (orders/referrals/discharge/follow-up)
```

## 4. Clinical and Operational Use Cases

### 4.1 High-priority use cases for first deployment waves

1. **ED triage orchestration**
   - Present in repo: triage + diagnosis + FHIR mediator.
   - Value: faster risk stratification and consistent escalation logic.
2. **Ambient/telemedicine documentation**
   - Present in repo: transcriber + summariser + EHR writer.
   - Value: reduced documentation burden and structured note quality.
3. **Consent and authorization checks**
   - Present in repo: provider + consent-analyser + insurer + HITL UI.
   - Value: fewer unauthorized data flows, explicit policy checkpoints.
4. **Public health surveillance**
   - Present in repo: hospital-reporting + OSINT + central synthesis.
   - Value: near real-time situational awareness and early outbreak alerts.

### 4.2 Expansion use cases (phase 2+)

1. Autonomous discharge planning.
2. Prior authorization packet generation.
3. Bed management and flow optimization.
4. Closed-loop chronic care outreach.
5. Revenue cycle anomaly triage.

### 4.3 Evidence from current literature (practical expectations)

Recent literature supports selective automation, but also shows that deployment quality matters more than model novelty:

1. **ED triage AI reviews** report meaningful potential for decision support, while emphasizing dataset bias, external validation gaps, and integration barriers.
2. **Hospital command center studies/reviews** show operational signal value, but mixed evidence on hard outcome improvement when governance and workflow redesign are weak.
3. **Ambient documentation (digital scribe) studies** show gains in documentation burden and usability metrics, but require rigorous safety/quality review for clinical note accuracy.
4. **Clinical LLM implementation reviews** increasingly point to governance, monitoring, and human oversight as primary determinants of safe benefit realization.

Implication for `nexus-a2a`: prioritize bounded, auditable agent pathways with prospective local validation before moving from assistive to autonomous actions.

## 5. Safety, Oversight, and Clinical Governance

### 5.1 Autonomy tiers

Adopt clear levels with increasing control rigor:

1. **Tier A (Assistive):** summarization, retrieval, coding suggestions.
2. **Tier B (Conditional Automation):** draft actions with clinician approval.
3. **Tier C (Protocol-bound Automation):** auto-actions within strict pathways.
4. **Tier D (High-risk recommendation):** mandatory dual control (human + policy).
5. **Tier E (Restricted):** prohibited or disabled workflows.

### 5.2 Mandatory safety controls for Tier C/D

1. Explicit "allowed action" schema (no free-form execution).
2. Hard policy gates before external side effects.
3. Minimum confidence + uncertainty thresholding.
4. Automatic fallback to manual pathway on any validation fault.
5. Full provenance chain for every output used in care decisions.
6. Real-time override and kill-switch capability.

### 5.3 Human oversight model

A practical HITL pattern already exists in `demos/compliance/hitl_agent/app/main.py`. Production-grade extension should include:

1. Risk-based queueing and SLA timers.
2. Role-based approver assignment.
3. Four-eyes control for high-severity actions.
4. Immutable approval records and rationale capture.

## 6. Security and Trust Architecture

### 6.1 Current baseline and immediate upgrades

Current baseline:

1. HS256 JWT auth (`shared/nexus_common/auth.py`).
2. Scope checks and bearer-token enforcement.
3. Did-verification hook exists but currently stubbed (`shared/nexus_common/did.py`).

Immediate production upgrades:

1. Move from shared symmetric secrets to asymmetric signing (per-agent keys, short-lived JWTs).
2. Add mTLS between agents.
3. Implement real DID/VC verification or enterprise PKI equivalent.
4. Enforce audience-bound tokens and anti-replay controls.
5. Centralize key rotation and revocation automation.

### 6.2 Cybersecurity control stack

Map to NIST CSF 2.0 and HHS healthcare cybersecurity performance goals:

1. Identity and access segmentation for each agent.
2. Asset inventory and software bill of materials.
3. Secure configuration baselines and immutable deployments.
4. Continuous logging, anomaly detection, and incident playbooks.
5. Backup, recovery drills, and downtime-safe manual fallbacks.

## 7. Data and Interoperability Strategy

### 7.1 Canonical clinical exchange

1. Use HL7 FHIR R4 as baseline payload model for broad compatibility.
2. Use SMART App Launch / OAuth profile for user- and app-context authorization.
3. Normalize internal agent payloads into a minimal canonical event model before dispatch.

### 7.2 Federated exchange and external trust

1. TEFCA-aligned connectivity for cross-network exchange (where applicable).
2. Explicit consent-state propagation with each task.
3. Data minimization by default: send only attributes required for each downstream action.

### 7.3 Data quality and provenance

Every agent output should include:

1. Input source references.
2. Transformation lineage.
3. Model/version metadata.
4. Confidence and uncertainty markers.
5. Validation status and policy decision outcome.

## 8. Regulatory and Standards Alignment (as of February 8, 2026)

### 8.1 United States

1. **ONC HTI-1 and subsequent HTI rulemaking**
   - Implication: autonomous workflows must preserve transparency and testability for decision-support artifacts.
2. **CMS Interoperability and Prior Authorization final rule**
   - Implication: payer-facing automation must be API-first, standards-based, and timeline-aware.
3. **HIPAA Security Rule NPRM (published January 6, 2025)**
   - Implication: design toward stronger required controls now; do not wait for finalization.
4. **NIST SP 800-66r2**
   - Implication: use as practical implementation mapping for HIPAA safeguards.
5. **FDA AI-enabled device and PCCP guidance**
   - Implication: if an agent function qualifies as device software, apply medical-device lifecycle controls.
6. **FDA QMSR effective February 2, 2026**
   - Implication: organizations developing regulated SaMD functions need quality system alignment.

### 8.2 European Union

1. **EU AI Act (entered into force August 1, 2024) with phased obligations**
   - Implication: classify hospital AI functions by risk and enforce human oversight/technical documentation accordingly.
2. **GDPR**
   - Implication: lawful basis, minimization, purpose limitation, and accountability must be machine-enforced in workflows.

### 8.3 International/Global guidance

1. **WHO Global Strategy on Digital Health extended to 2027**
   - Implication: architecture should support equity, interoperability, and scalable national governance.
2. **WHO AI ethics and governance guidance**
   - Implication: embed transparency, responsibility, and safety-by-design in deployment policy.

## 9. Governance Operating Model

### 9.1 Decision rights

1. **Clinical Governance Board**
   - Owns autonomy tiers, acceptable-risk thresholds, and override policies.
2. **Digital Safety Office**
   - Owns validation protocols, incident classification, and release gates.
3. **Security and Privacy Office**
   - Owns trust architecture, key management, and compliance evidence.
4. **Service Line Owners**
   - Own workflow outcomes, operational KPIs, and adoption.

### 9.2 Required governance artifacts

1. Agent inventory and risk register.
2. Model cards and intended-use declarations.
3. Validation and drift-monitoring plans.
4. HITL policy catalog.
5. Incident response runbooks by autonomy tier.

## 10. Implementation Roadmap

### Phase 0 (0-90 days): Foundation hardening

1. Stabilize protocol and auth contracts.
2. Resolve failing conformance scenarios and enforce CI gates.
3. Deploy centralized telemetry and immutable audit logging.
4. Define autonomy tiers and policy catalog.

### Phase 1 (3-6 months): Low-risk autonomy in production

1. Deploy telemed documentation and administrative orchestration.
2. Implement HITL queueing for all medium/high-risk actions.
3. Instrument baseline KPIs and clinical quality counters.

### Phase 2 (6-12 months): Clinical pathway pilots

1. Launch ED triage support in controlled units.
2. Add FHIR and external exchange connectors.
3. Run prospective silent-mode validation before auto-action enablement.

### Phase 3 (12-24 months): Networked digital hospital operations

1. Expand to discharge, referrals, prior auth, and follow-up automation.
2. Add resilience patterns (store-and-forward, graceful degradation).
3. Integrate command-center operations with autonomy dashboards.

## 11. KPI and Value Framework

### 11.1 Clinical and patient outcomes

1. Time-to-triage and time-to-disposition.
2. Escalation appropriateness rate.
3. Follow-up completion rate.
4. Safety event rate (per autonomy tier).

### 11.2 Workforce and operational outcomes

1. Documentation time per encounter.
2. Queue turnaround time for authorization and referrals.
3. Bed turnover and boarding metrics.
4. Agent-handled vs. manually handled task ratio.

### 11.3 Governance and trust outcomes

1. HITL compliance rate for high-risk tasks.
2. Audit completeness and traceability score.
3. Security control coverage and incident MTTR.
4. Model drift detection-to-mitigation cycle time.

## 12. Key Risks and Mitigations

1. **Risk:** Model-generated unsafe recommendations.
   - **Mitigation:** constrained action schemas, policy gates, mandatory HITL by tier.
2. **Risk:** Security compromise across agent mesh.
   - **Mitigation:** zero-trust segmentation, mTLS, short-lived tokens, key rotation.
3. **Risk:** Regulatory non-conformance due evolving rules.
   - **Mitigation:** policy-as-code with versioned controls and quarterly legal/technical updates.
4. **Risk:** Vendor/API fragility.
   - **Mitigation:** adapter abstraction, fallback providers, deterministic degradation paths.
5. **Risk:** Workflow brittleness and staff rejection.
   - **Mitigation:** service-line co-design, override UX, transparent incident feedback loops.

## 13. Immediate Priorities for This Repository

To convert `nexus-a2a` from reference implementation to deployable platform:

1. Close the conformance gap (`55 pass / 55 fail / 30 skip`) and enforce a release threshold.
2. Replace DID verification stub with real cryptographic verification.
3. Introduce asymmetric JWT or mTLS-based service identity.
4. Add explicit policy engine service for risk scoring + approval routing.
5. Add immutable audit event pipeline and retention policy.
6. Extend compliance suite to map each requirement to runtime evidence artifacts.

## 14. Conclusion

An autonomous digital hospital is achievable when autonomy is treated as a governed systems capability, not a model feature. `nexus-a2a` already provides a credible substrate: composable agent workflows, interoperable task contracts, and a path to compliance-grade verification. The critical next step is disciplined production hardening across trust, safety, and conformance so that automation improves access, quality, and resilience without compromising clinical accountability.

## References

1. A2A Protocol website: https://a2aprotocol.ai/  
2. A2A specification repository: https://github.com/a2aproject/A2A/tree/main/specification  
3. ONC HTI rules overview: https://healthit.gov/regulations/hti-rules/  
4. ONC HTI-1 Final Rule page: https://healthit.gov/regulations/hti-rules/hti-1-final-rule/  
5. CMS Interoperability and Prior Authorization final rule fact sheet: https://www.cms.gov/newsroom/fact-sheets/cms-interoperability-and-prior-authorization-final-rule-cms-0057-f  
6. OCR HIPAA Security Rule NPRM (published January 6, 2025): https://www.hhs.gov/hipaa/for-professionals/security/nprm-cybersecurity/index.html  
7. Federal Register entry for HIPAA Security Rule NPRM: https://www.federalregister.gov/documents/2025/01/06/2024-30928/security-standards-for-the-protection-of-electronic-protected-health-information  
8. NIST AI Risk Management Framework (AI RMF 1.0): https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-ai-rmf-10  
9. NIST Cybersecurity Framework 2.0: https://www.nist.gov/cyberframework  
10. NIST SP 800-66r2 (Implementing the HIPAA Security Rule): https://www.nist.gov/publications/implementing-health-insurance-portability-and-accountability-act-hipaa-security-rule  
11. HHS Healthcare and Public Health Cybersecurity Performance Goals: https://www.hhs.gov/about/news/2024/01/24/hhs-releases-voluntary-healthcare-cybersecurity-performance-goals.html  
12. HHS 405(d) HPH CPG resources: https://405d.hhs.gov/cpgs/  
13. FDA Predetermined Change Control Plan (PCCP) guidance for AI-enabled device software: https://www.fda.gov/regulatory-information/search-fda-guidance-documents/marketing-submission-recommendations-predetermined-change-control-plan-artificial-intelligence-enabled-device-software-functions  
14. FDA AI/ML-Enabled Medical Devices list: https://www.fda.gov/medical-devices/software-medical-device-samd/artificial-intelligence-and-machine-learning-aiml-enabled-medical-devices  
15. FDA Quality Management System Regulation (QMSR) final rule: https://www.federalregister.gov/documents/2024/02/02/2024-01709/medical-devices-quality-system-regulation-amendments  
16. European Commission AI Act portal (timeline and implementation): https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai  
17. EUR-Lex AI Act legal text: https://eur-lex.europa.eu/eli/reg/2024/1689/oj  
18. WHO Global Strategy on Digital Health extension to 2027 (WHA78.5): https://www.who.int/news/item/26-05-2025-seventy-eighth-world-health-assembly---daily-update--26-may-2025  
19. WHO guidance on Ethics and Governance of AI for Health: https://www.who.int/publications/i/item/9789240029200  
20. HL7 FHIR R4 base specification: https://hl7.org/fhir/R4/  
21. HL7 SMART App Launch implementation guide: https://build.fhir.org/ig/HL7/smart-app-launch/  
22. TEFCA policy and QHIN framework overview: https://healthit.gov/policy/tefca/  
23. BMC Emergency Medicine (2024), systematic review on AI in ED triage: https://bmcemergmed.biomedcentral.com/articles/10.1186/s12873-024-01135-2  
24. JAMA Network Open (2025), ambient AI documentation support in primary care: https://jamanetwork.com/journals/jamanetworkopen/fullarticle/10.1001/jamanetworkopen.2025.34976  
25. BMJ Health & Care Informatics (2023), hospital command centres study: https://informatics.bmj.com/content/30/1/e100653  
26. Journal of Patient Safety (2022), scoping review of hospital command centers: https://pubmed.ncbi.nlm.nih.gov/35435429/  
27. npj Digital Medicine (2025), clinical implementation of LLMs scoping review: https://www.nature.com/articles/s41746-025-01565-7  
