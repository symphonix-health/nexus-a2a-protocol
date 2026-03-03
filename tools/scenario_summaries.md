# HelixCare Patient Journey Scenarios

Generated: 2026-03-03 15:57:42

Total Scenarios: 43

## Scenario Overview

### 1. Primary Care Outpatient In Person

**Description:** In-person primary care visit with assessment, treatment, and checkout.

**Patient Profile:**
- Age: 47
- Gender: female
- Chief Complaint: Fatigue and elevated blood pressure follow-up
- Urgency: medium

**Journey Steps:** 6

1. **Primary Care** - primary_care/manage_visit
2. **Clinician Avatar** - avatar/start_session
3. **Clinician Avatar** - avatar/patient_message
4. **Diagnosis** - tasks/sendSubscribe
5. **Pharmacy** - pharmacy/recommend
6. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~16 seconds

---

### 2. Specialty Outpatient Clinic

**Description:** Specialty clinic workflow with referral triage and diagnostics.

**Patient Profile:**
- Age: 61
- Gender: male
- Chief Complaint: Progressive exertional chest discomfort
- Urgency: high

**Journey Steps:** 6

1. **Specialty Care** - specialty_care/manage_referral
2. **Clinician Avatar** - avatar/start_session
3. **Clinician Avatar** - avatar/patient_message
4. **Diagnosis** - tasks/sendSubscribe
5. **Imaging** - tasks/sendSubscribe
6. **Coordinator** - tasks/sendSubscribe

**Expected Duration:** ~18 seconds

---

### 3. Telehealth Video Consult

**Description:** Video telehealth consult with identity/location verification and remote plan.

**Patient Profile:**
- Age: 35
- Gender: female
- Chief Complaint: Migraine follow-up
- Urgency: low

**Journey Steps:** 6

1. **Telehealth** - telehealth/consult
2. **Clinician Avatar** - avatar/start_session
3. **Clinician Avatar** - avatar/patient_message
4. **Diagnosis** - tasks/sendSubscribe
5. **Pharmacy** - pharmacy/recommend
6. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~14 seconds

---

### 4. Telehealth Audio Only Followup

**Description:** Audio-only telehealth follow-up with escalation guardrails.

**Patient Profile:**
- Age: 73
- Gender: male
- Chief Complaint: Medication side-effect review
- Urgency: low

**Journey Steps:** 6

1. **Telehealth** - telehealth/consult
2. **Clinician Avatar** - avatar/start_session
3. **Clinician Avatar** - avatar/patient_message
4. **Primary Care** - primary_care/manage_visit
5. **Pharmacy** - pharmacy/check_interactions
6. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~13 seconds

---

### 5. Home Visit House Call

**Description:** Home-based primary care visit including environment and safety assessment.

**Patient Profile:**
- Age: 84
- Gender: female
- Chief Complaint: Frailty and recurrent falls
- Urgency: medium

**Journey Steps:** 6

1. **Home Visit** - home_visit/dispatch
2. **Clinician Avatar** - avatar/start_session
3. **Clinician Avatar** - avatar/patient_message
4. **Primary Care** - primary_care/manage_visit
5. **Pharmacy** - pharmacy/recommend
6. **Coordinator** - tasks/sendSubscribe

**Expected Duration:** ~19 seconds

---

### 6. Chronic Care Management Monthly

**Description:** Longitudinal CCM monthly cycle with care-plan update and coordination.

**Patient Profile:**
- Age: 69
- Gender: male
- Chief Complaint: CCM monthly review for diabetes and CHF
- Urgency: low

**Journey Steps:** 6

1. **Ccm** - ccm/monthly_review
2. **Clinician Avatar** - avatar/start_session
3. **Clinician Avatar** - avatar/patient_message
4. **Primary Care** - primary_care/manage_visit
5. **Followup** - tasks/sendSubscribe
6. **Pharmacy** - pharmacy/check_interactions

**Expected Duration:** ~15 seconds

---

### 7. Emergency Department Treat And Release

**Description:** ED flow resulting in treatment and safe discharge.

**Patient Profile:**
- Age: 29
- Gender: male
- Chief Complaint: Acute asthma exacerbation
- Urgency: high

**Journey Steps:** 8

1. **Triage** - tasks/sendSubscribe
2. **Clinician Avatar** - avatar/start_session
3. **Clinician Avatar** - avatar/patient_message
4. **Diagnosis** - tasks/sendSubscribe
5. **Imaging** - tasks/sendSubscribe
6. **Pharmacy** - tasks/sendSubscribe
7. **Discharge** - tasks/sendSubscribe
8. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~20 seconds

---

### 8. Emergency Department To Inpatient Admission

**Description:** ED flow that escalates to inpatient admission.

**Patient Profile:**
- Age: 57
- Gender: female
- Chief Complaint: Chest pain and diaphoresis
- Urgency: critical

**Journey Steps:** 7

1. **Triage** - tasks/sendSubscribe
2. **Clinician Avatar** - avatar/start_session
3. **Clinician Avatar** - avatar/patient_message
4. **Diagnosis** - tasks/sendSubscribe
5. **Imaging** - tasks/sendSubscribe
6. **Bed Manager** - tasks/sendSubscribe
7. **Coordinator** - tasks/sendSubscribe

**Expected Duration:** ~18 seconds

---

### 9. Inpatient Admission And Daily Rounds

**Description:** Inpatient episode focusing on admission, medication safety, and daily review.

**Patient Profile:**
- Age: 72
- Gender: male
- Chief Complaint: Community acquired pneumonia with hypoxia
- Urgency: high

**Journey Steps:** 6

1. **Bed Manager** - admission/assign_bed
2. **Clinician Avatar** - avatar/start_session
3. **Clinician Avatar** - avatar/patient_message
4. **Pharmacy** - tasks/sendSubscribe
5. **Coordinator** - tasks/sendSubscribe
6. **Ccm** - ccm/monthly_review

**Expected Duration:** ~16 seconds

---

### 10. Inpatient Discharge Transition

**Description:** Discharge and transition-of-care workflow to outpatient follow-up.

**Patient Profile:**
- Age: 66
- Gender: female
- Chief Complaint: Discharge readiness after CHF admission
- Urgency: medium

**Journey Steps:** 6

1. **Clinician Avatar** - avatar/start_session
2. **Clinician Avatar** - avatar/patient_message
3. **Discharge** - tasks/sendSubscribe
4. **Pharmacy** - pharmacy/recommend
5. **Followup** - tasks/sendSubscribe
6. **Ccm** - ccm/monthly_review

**Expected Duration:** ~15 seconds

---

### 11. Chest Pain Cardiac

**Description:** Adult with severe chest pain and suspected acute coronary syndrome.

**Patient Profile:**
- Age: 55
- Gender: male
- Chief Complaint: Severe chest pain with dyspnea
- Urgency: high

**Journey Steps:** 7

1. **Triage** - tasks/sendSubscribe
2. **Clinician Avatar** - avatar/start_session
3. **Clinician Avatar** - avatar/patient_message
4. **Diagnosis** - tasks/sendSubscribe
5. **Imaging** - tasks/sendSubscribe
6. **Pharmacy** - tasks/sendSubscribe
7. **Bed Manager** - tasks/sendSubscribe

**Expected Duration:** ~22 seconds

---

### 12. Pediatric Fever Sepsis

**Description:** Child with high fever and lethargy requiring sepsis workup.

**Patient Profile:**
- Age: 3
- Gender: female
- Chief Complaint: High fever and poor feeding
- Urgency: high

**Journey Steps:** 6

1. **Triage** - tasks/sendSubscribe
2. **Clinician Avatar** - avatar/start_session
3. **Clinician Avatar** - avatar/patient_message
4. **Diagnosis** - tasks/sendSubscribe
5. **Pharmacy** - tasks/sendSubscribe
6. **Bed Manager** - tasks/sendSubscribe

**Expected Duration:** ~18 seconds

---

### 13. Orthopedic Fracture

**Description:** Extremity fracture workflow with imaging, pain control, and follow-up.

**Patient Profile:**
- Age: 28
- Gender: male
- Chief Complaint: Left leg pain after fall
- Urgency: medium

**Journey Steps:** 7

1. **Triage** - tasks/sendSubscribe
2. **Clinician Avatar** - avatar/start_session
3. **Clinician Avatar** - avatar/patient_message
4. **Diagnosis** - tasks/sendSubscribe
5. **Imaging** - tasks/sendSubscribe
6. **Discharge** - tasks/sendSubscribe
7. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~16 seconds

---

### 14. Geriatric Confusion

**Description:** Elderly patient with acute confusion and delirium-focused pathway.

**Patient Profile:**
- Age: 78
- Gender: female
- Chief Complaint: Sudden confusion and agitation
- Urgency: high

**Journey Steps:** 6

1. **Triage** - tasks/sendSubscribe
2. **Clinician Avatar** - avatar/start_session
3. **Clinician Avatar** - avatar/patient_message
4. **Diagnosis** - tasks/sendSubscribe
5. **Imaging** - tasks/sendSubscribe
6. **Bed Manager** - tasks/sendSubscribe

**Expected Duration:** ~17 seconds

---

### 15. Obstetric Emergency

**Description:** Pregnancy bleeding emergency with urgent maternal/fetal coordination.

**Patient Profile:**
- Age: 32
- Gender: female
- Chief Complaint: Bleeding at 28 weeks gestation
- Urgency: critical

**Journey Steps:** 6

1. **Triage** - tasks/sendSubscribe
2. **Clinician Avatar** - avatar/start_session
3. **Clinician Avatar** - avatar/patient_message
4. **Diagnosis** - tasks/sendSubscribe
5. **Imaging** - tasks/sendSubscribe
6. **Bed Manager** - tasks/sendSubscribe

**Expected Duration:** ~16 seconds

---

### 16. Mental Health Crisis

**Description:** Acute psychiatric crisis with safety and inpatient behavioral health planning.

**Patient Profile:**
- Age: 35
- Gender: male
- Chief Complaint: Suicidal thoughts
- Urgency: critical

**Journey Steps:** 5

1. **Triage** - tasks/sendSubscribe
2. **Clinician Avatar** - avatar/start_session
3. **Clinician Avatar** - avatar/patient_message
4. **Diagnosis** - tasks/sendSubscribe
5. **Bed Manager** - tasks/sendSubscribe

**Expected Duration:** ~15 seconds

---

### 17. Chronic Diabetes Complication

**Description:** Diabetic foot complication needing multidisciplinary inpatient planning.

**Patient Profile:**
- Age: 62
- Gender: female
- Chief Complaint: Foot ulcer with infection
- Urgency: medium

**Journey Steps:** 6

1. **Clinician Avatar** - avatar/start_session
2. **Clinician Avatar** - avatar/patient_message
3. **Diagnosis** - tasks/sendSubscribe
4. **Imaging** - tasks/sendSubscribe
5. **Pharmacy** - tasks/sendSubscribe
6. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~17 seconds

---

### 18. Trauma Motor Vehicle Accident

**Description:** Polytrauma workflow from high-speed MVC.

**Patient Profile:**
- Age: 25
- Gender: male
- Chief Complaint: Multiple traumatic injuries
- Urgency: critical

**Journey Steps:** 6

1. **Triage** - tasks/sendSubscribe
2. **Clinician Avatar** - avatar/start_session
3. **Clinician Avatar** - avatar/patient_message
4. **Diagnosis** - tasks/sendSubscribe
5. **Imaging** - tasks/sendSubscribe
6. **Bed Manager** - tasks/sendSubscribe

**Expected Duration:** ~17 seconds

---

### 19. Infectious Disease Outbreak

**Description:** Respiratory outbreak case requiring isolation and public health escalation.

**Patient Profile:**
- Age: 45
- Gender: female
- Chief Complaint: Fever, cough, hypoxia
- Urgency: high

**Journey Steps:** 4

1. **Triage** - tasks/sendSubscribe
2. **Diagnosis** - tasks/sendSubscribe
3. **Imaging** - tasks/sendSubscribe
4. **Bed Manager** - tasks/sendSubscribe

**Expected Duration:** ~12 seconds

---

### 20. Pediatric Asthma Exacerbation

**Description:** Severe pediatric asthma exacerbation with acute stabilization and follow-up.

**Patient Profile:**
- Age: 8
- Gender: male
- Chief Complaint: Severe wheeze and shortness of breath
- Urgency: high

**Journey Steps:** 6

1. **Triage** - tasks/sendSubscribe
2. **Clinician Avatar** - avatar/start_session
3. **Clinician Avatar** - avatar/patient_message
4. **Diagnosis** - tasks/sendSubscribe
5. **Pharmacy** - tasks/sendSubscribe
6. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~16 seconds

---

### 21. Regional Hie Referral Exchange

**Description:** ED-to-regional referral with OpenHIE mediation and coordinator handoff.

**Patient Profile:**
- Age: 52
- Gender: male
- Chief Complaint: TIA symptoms requiring cross-network referral
- Urgency: high

**Journey Steps:** 4

1. **Triage** - tasks/sendSubscribe
2. **Diagnosis** - tasks/sendSubscribe
3. **Openhie Mediator** - tasks/sendSubscribe
4. **Coordinator** - tasks/sendSubscribe

**Expected Duration:** ~12 seconds

---

### 22. Telemed Scribe Documentation Chain

**Description:** Telemedicine encounter routed through transcriber, summariser, and EHR writer agents.

**Patient Profile:**
- Age: 41
- Gender: female
- Chief Complaint: Persistent sinus pain after URI
- Urgency: medium

**Journey Steps:** 5

1. **Telehealth** - telehealth/consult
2. **Transcriber** - tasks/sendSubscribe
3. **Summariser** - tasks/sendSubscribe
4. **Ehr Writer** - tasks/sendSubscribe
5. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~13 seconds

---

### 23. Consent And Payer Authorization

**Description:** Consent verification and payer pre-authorization with HITL adjudication.

**Patient Profile:**
- Age: 58
- Gender: female
- Chief Complaint: MRI authorization for persistent radiculopathy
- Urgency: medium

**Journey Steps:** 5

1. **Provider Agent** - tasks/sendSubscribe
2. **Insurer Agent** - tasks/sendSubscribe
3. **Consent Analyser** - tasks/sendSubscribe
4. **Hitl Ui** - tasks/sendSubscribe
5. **Imaging** - tasks/sendSubscribe

**Expected Duration:** ~14 seconds

---

### 24. New Patient Registration To Consult

**Description:** First-time patient journey with provider-side registration, insurance eligibility verification, and assisted enrollment before clinical consultation.

**Patient Profile:**
- Age: 33
- Gender: female
- Chief Complaint: Persistent lower abdominal pain and dizziness
- Urgency: medium

**Journey Steps:** 10

1. **Provider Agent** - tasks/sendSubscribe
2. **Hitl Ui** - tasks/sendSubscribe
3. **Insurer Agent** - tasks/sendSubscribe
4. **Consent Analyser** - tasks/sendSubscribe
5. **Triage** - tasks/sendSubscribe
6. **Clinician Avatar** - avatar/start_session
7. **Clinician Avatar** - avatar/patient_message
8. **Diagnosis** - tasks/sendSubscribe
9. **Pharmacy** - pharmacy/recommend
10. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~17 seconds

---

### 25. Registration Failed Urgent Clinical Override

**Description:** Negative-path journey where registration and coverage verification fail, but urgent clinical override permits emergency treatment while coverage remains pending.

**Patient Profile:**
- Age: 41
- Gender: male
- Chief Complaint: Severe chest pain and shortness of breath
- Urgency: critical

**Journey Steps:** 10

1. **Provider Agent** - tasks/sendSubscribe
2. **Insurer Agent** - tasks/sendSubscribe
3. **Hitl Ui** - tasks/sendSubscribe
4. **Triage** - tasks/sendSubscribe
5. **Clinician Avatar** - avatar/start_session
6. **Clinician Avatar** - avatar/patient_message
7. **Diagnosis** - tasks/sendSubscribe
8. **Pharmacy** - pharmacy/recommend
9. **Bed Manager** - tasks/sendSubscribe
10. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~18 seconds

---

### 26. Notifiable Outbreak Public Health Loop

**Description:** Hospital case escalated to public health surveillance with OSINT corroboration.

**Patient Profile:**
- Age: 46
- Gender: male
- Chief Complaint: Severe febrile respiratory illness with cluster exposure
- Urgency: high

**Journey Steps:** 4

1. **Hospital Reporter** - tasks/sendSubscribe
2. **Osint Agent** - tasks/sendSubscribe
3. **Central Surveillance** - tasks/sendSubscribe
4. **Bed Manager** - tasks/sendSubscribe

**Expected Duration:** ~11 seconds

---

### 27. Clinician Avatar Consultation

**Description:** Clinician avatar conducts a Calgary-Cambridge structured interview with a chest-pain patient.

**Patient Profile:**
- Age: 54
- Gender: male
- Chief Complaint: Intermittent chest tightness with exertion
- Urgency: high

**Journey Steps:** 8

1. **Triage** - tasks/sendSubscribe
2. **Clinician Avatar** - avatar/start_session
3. **Clinician Avatar** - avatar/patient_message
4. **Clinician Avatar** - avatar/patient_message
5. **Diagnosis** - tasks/sendSubscribe
6. **Imaging** - tasks/sendSubscribe
7. **Pharmacy** - pharmacy/recommend
8. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~18 seconds

---

### 28. Clinician Avatar Uk Gp Consultation

**Description:** UK primary-care consultation via the Clinician Avatar using the GP persona (P002). Patient presents with persistent cough and breathlessness — the avatar interviews using Calgary-Cambridge, then delegates diagnosis.

**Patient Profile:**
- Age: 38
- Gender: female
- Chief Complaint: Persistent cough for 3 weeks
- Urgency: low

**Journey Steps:** 5

1. **Clinician Avatar** - avatar/start_session
2. **Clinician Avatar** - avatar/patient_message
3. **Clinician Avatar** - avatar/patient_message
4. **Diagnosis** - tasks/sendSubscribe
5. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~12 seconds

---

### 29. Clinician Avatar Usa Attending Acs

**Description:** USA hospital consultation using the Attending Physician persona (P014). Patient presents with suspected ACS — avatar uses SOCRATES framework, then delegates to diagnosis and imaging.

**Patient Profile:**
- Age: 62
- Gender: male
- Chief Complaint: Severe crushing chest pain radiating to left arm
- Urgency: high

**Journey Steps:** 5

1. **Clinician Avatar** - avatar/start_session
2. **Clinician Avatar** - avatar/patient_message
3. **Clinician Avatar** - avatar/patient_message
4. **Triage** - tasks/sendSubscribe
5. **Diagnosis** - tasks/sendSubscribe

**Expected Duration:** ~14 seconds

---

### 30. Clinician Avatar Kenya Medical Officer

**Description:** Kenya health facility consultation using the Medical Officer persona (P026). Paediatric patient with high fever and vomiting — potential malaria or typhoid.

**Patient Profile:**
- Age: 7
- Gender: male
- Chief Complaint: High fever for 2 days and vomiting
- Urgency: high

**Journey Steps:** 5

1. **Clinician Avatar** - avatar/start_session
2. **Clinician Avatar** - avatar/patient_message
3. **Clinician Avatar** - avatar/patient_message
4. **Diagnosis** - tasks/sendSubscribe
5. **Pharmacy** - pharmacy/recommend

**Expected Duration:** ~10 seconds

---

### 31. Clinician Avatar Telehealth Uk Followup

**Description:** UK telehealth consultation using the Telehealth Clinician persona (P048). Post-discharge remote follow-up for a frailty patient — avatar interviews then escalates care plan update to CCM agent.

**Patient Profile:**
- Age: 78
- Gender: female
- Chief Complaint: Post-discharge follow-up — mobility and medication review
- Urgency: low

**Journey Steps:** 5

1. **Clinician Avatar** - avatar/start_session
2. **Clinician Avatar** - avatar/patient_message
3. **Clinician Avatar** - avatar/patient_message
4. **Care Coordinator** - tasks/sendSubscribe
5. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~14 seconds

---

### 32. Clinician Avatar Psychiatrist Mental Health

**Description:** Mental health consultation using the Psychiatrist persona (P065). Patient with depressive episode and anxiety — avatar uses Calgary-Cambridge with trauma-informed approach, then delegates to care coordinator.

**Patient Profile:**
- Age: 29
- Gender: female
- Chief Complaint: Persistent low mood and anxiety for 6 months
- Urgency: medium

**Journey Steps:** 5

1. **Clinician Avatar** - avatar/start_session
2. **Clinician Avatar** - avatar/patient_message
3. **Clinician Avatar** - avatar/patient_message
4. **Care Coordinator** - tasks/sendSubscribe
5. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~16 seconds

---

### 33. Multi Agent Delegation Chest Pain Iam

**Description:** Demonstrates the full delegation chain for a chest pain scenario with IAM persona context. Avatar (P001) → Care Coordinator (P021) → Triage (P004) → Diagnosis (P001) → Imaging (P005). Tests that each handoff respects persona scopes and delegation policy.

**Patient Profile:**
- Age: 55
- Gender: male
- Chief Complaint: Crushing chest pain, 45 minutes, radiation to jaw
- Urgency: critical

**Journey Steps:** 6

1. **Clinician Avatar** - avatar/start_session
2. **Clinician Avatar** - avatar/patient_message
3. **Triage** - tasks/sendSubscribe
4. **Diagnosis** - tasks/sendSubscribe
5. **Imaging** - tasks/sendSubscribe
6. **Pharmacy** - pharmacy/recommend

**Expected Duration:** ~12 seconds

---

### 34. Interop Eligibility Prior Auth Bridge

**Description:** Cross-standard prior authorization pathway: registry-driven profile resolution, FHIR clinical packet validation, X12 eligibility/prior-auth translation, and audit trail emission.

**Patient Profile:**
- Age: 57
- Gender: female
- Chief Complaint: Progressive lumbar radiculopathy requiring MRI authorization
- Urgency: medium

**Journey Steps:** 6

1. **Provider Agent** - tasks/sendSubscribe
2. **Profile Registry** - tasks/sendSubscribe
3. **Fhir Profile** - tasks/sendSubscribe
4. **X12 Gateway** - tasks/sendSubscribe
5. **Insurer Agent** - tasks/sendSubscribe
6. **Audit** - tasks/sendSubscribe

**Expected Duration:** ~14 seconds

---

### 35. Interop Claim Submission And Remittance

**Description:** Post-discharge billing flow that converts a FHIR Claim to X12 837, ingests 835 remittance, maps outcomes back to financial records, and logs immutable audit evidence.

**Patient Profile:**
- Age: 63
- Gender: male
- Chief Complaint: Heart-failure admission billing and reconciliation
- Urgency: low

**Journey Steps:** 6

1. **Discharge** - tasks/sendSubscribe
2. **Profile Registry** - tasks/sendSubscribe
3. **Fhir Profile** - tasks/sendSubscribe
4. **X12 Gateway** - tasks/sendSubscribe
5. **Care Coordinator** - tasks/sendSubscribe
6. **Audit** - tasks/sendSubscribe

**Expected Duration:** ~13 seconds

---

### 36. Interop Pharmacy Pos Claim Adjudication

**Description:** Outpatient pharmacy point-of-sale claim using NCPDP Telecom D.0 with profile registry resolution, adjudication response handling, and audit trace emission.

**Patient Profile:**
- Age: 49
- Gender: female
- Chief Complaint: Urgent insulin refill after dose adjustment
- Urgency: medium

**Journey Steps:** 6

1. **Pharmacy** - pharmacy/recommend
2. **Profile Registry** - tasks/sendSubscribe
3. **Ncpdp Gateway** - tasks/sendSubscribe
4. **Fhir Profile** - tasks/sendSubscribe
5. **Audit** - tasks/sendSubscribe
6. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~12 seconds

---

### 37. Interop Unsupported Profile Routing Failure

**Description:** Negative-path intake where a requested interoperability profile is unsupported, causing deterministic routing failure, manual escalation, and audited closure.

**Patient Profile:**
- Age: 44
- Gender: female
- Chief Complaint: Specialty referral requiring unsupported payer profile
- Urgency: medium

**Journey Steps:** 4

1. **Provider Agent** - tasks/sendSubscribe
2. **Profile Registry** - tasks/sendSubscribe
3. **Hitl Ui** - tasks/sendSubscribe
4. **Audit** - tasks/sendSubscribe

**Expected Duration:** ~9 seconds

---

### 38. Interop Profile Fallback Exhaustion

**Description:** Negative-path prior-auth flow where acceptable profile fallback options are exhausted without compatible SemVer matches, forcing safe interruption and audit evidence.

**Patient Profile:**
- Age: 61
- Gender: male
- Chief Complaint: Planned lumbar procedure prior-auth with stale partner profiles
- Urgency: low

**Journey Steps:** 4

1. **Provider Agent** - tasks/sendSubscribe
2. **Profile Registry** - tasks/sendSubscribe
3. **Care Coordinator** - tasks/sendSubscribe
4. **Audit** - tasks/sendSubscribe

**Expected Duration:** ~9 seconds

---

### 39. Interop Malformed Ncpdp Payload

**Description:** Negative-path pharmacy claim where malformed NCPDP payload fields are detected, rejected safely, corrected via human review, and audited.

**Patient Profile:**
- Age: 52
- Gender: female
- Chief Complaint: Urgent insulin refill with malformed payer payload
- Urgency: high

**Journey Steps:** 5

1. **Pharmacy** - pharmacy/recommend
2. **Profile Registry** - tasks/sendSubscribe
3. **Ncpdp Gateway** - tasks/sendSubscribe
4. **Hitl Ui** - tasks/sendSubscribe
5. **Audit** - tasks/sendSubscribe

**Expected Duration:** ~10 seconds

---

### 40. Interop X12 Translation Reject Loop

**Description:** Negative-path claims flow where X12 translation triggers repeated partner rejects, enters bounded retry loop, then escalates to safe manual reconciliation.

**Patient Profile:**
- Age: 66
- Gender: male
- Chief Complaint: Post-discharge claim repeatedly rejected by clearinghouse
- Urgency: low

**Journey Steps:** 6

1. **Discharge** - tasks/sendSubscribe
2. **Profile Registry** - tasks/sendSubscribe
3. **Fhir Profile** - tasks/sendSubscribe
4. **X12 Gateway** - tasks/sendSubscribe
5. **Care Coordinator** - tasks/sendSubscribe
6. **Audit** - tasks/sendSubscribe

**Expected Duration:** ~11 seconds

---

### 41. Interop Hl7V2 Adt Patient Merge

**Description:** HL7 V2 ADT^A40 patient merge from legacy hospital system with FHIR translation.

**Patient Profile:**
- Age: 62
- Gender: female
- Chief Complaint: Duplicate patient records identified during registration
- Urgency: administrative

**Journey Steps:** 4

1. **Profile Registry** - tasks/sendSubscribe
2. **Hl7V2 Gateway** - tasks/sendSubscribe
3. **Fhir Profile** - tasks/sendSubscribe
4. **Audit** - tasks/sendSubscribe

**Expected Duration:** ~4 seconds

---

### 42. Interop Cda Discharge Summary Hie

**Description:** C-CDA Discharge Summary generation and submission to state HIE network.

**Patient Profile:**
- Age: 71
- Gender: male
- Chief Complaint: Post-discharge document exchange to regional HIE
- Urgency: routine

**Journey Steps:** 5

1. **Discharge** - tasks/sendSubscribe
2. **Profile Registry** - tasks/sendSubscribe
3. **Cda Document** - tasks/sendSubscribe
4. **Fhir Profile** - tasks/sendSubscribe
5. **Audit** - tasks/sendSubscribe

**Expected Duration:** ~6 seconds

---

### 43. Interop Dicom Radiology Telehealth Consult

**Description:** DICOM imaging study query and ImagingStudy FHIR mapping for telehealth radiology consult.

**Patient Profile:**
- Age: 48
- Gender: female
- Chief Complaint: Persistent headaches requiring imaging review
- Urgency: routine

**Journey Steps:** 6

1. **Imaging** - tasks/sendSubscribe
2. **Profile Registry** - tasks/sendSubscribe
3. **Dicom Imaging** - tasks/sendSubscribe
4. **Fhir Profile** - tasks/sendSubscribe
5. **Specialty Care** - tasks/sendSubscribe
6. **Audit** - tasks/sendSubscribe

**Expected Duration:** ~7 seconds

---

## Agent Coverage

The following agents are exercised across all scenarios:

- **Audit**
- **Bed Manager**
- **Care Coordinator**
- **Ccm**
- **Cda Document**
- **Central Surveillance**
- **Clinician Avatar**
- **Consent Analyser**
- **Coordinator**
- **Diagnosis**
- **Dicom Imaging**
- **Discharge**
- **Ehr Writer**
- **Fhir Profile**
- **Followup**
- **Hitl Ui**
- **Hl7V2 Gateway**
- **Home Visit**
- **Hospital Reporter**
- **Imaging**
- **Insurer Agent**
- **Ncpdp Gateway**
- **Openhie Mediator**
- **Osint Agent**
- **Pharmacy**
- **Primary Care**
- **Profile Registry**
- **Provider Agent**
- **Specialty Care**
- **Summariser**
- **Telehealth**
- **Transcriber**
- **Triage**
- **X12 Gateway**

**Total Agents:** 34
