# HelixCare Patient Journey Scenarios

Generated: 2026-02-19 18:32:19

Total Scenarios: 24

## Scenario Overview

### 1. Primary Care Outpatient In Person

**Description:** In-person primary care visit with assessment, treatment, and checkout.

**Patient Profile:**
- Age: 47
- Gender: female
- Chief Complaint: Fatigue and elevated blood pressure follow-up
- Urgency: medium

**Journey Steps:** 4

1. **Primary Care** - primary_care/manage_visit
2. **Diagnosis** - tasks/sendSubscribe
3. **Pharmacy** - pharmacy/recommend
4. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~12 seconds

---

### 2. Specialty Outpatient Clinic

**Description:** Specialty clinic workflow with referral triage and diagnostics.

**Patient Profile:**
- Age: 61
- Gender: male
- Chief Complaint: Progressive exertional chest discomfort
- Urgency: high

**Journey Steps:** 4

1. **Specialty Care** - specialty_care/manage_referral
2. **Diagnosis** - tasks/sendSubscribe
3. **Imaging** - tasks/sendSubscribe
4. **Coordinator** - tasks/sendSubscribe

**Expected Duration:** ~14 seconds

---

### 3. Telehealth Video Consult

**Description:** Video telehealth consult with identity/location verification and remote plan.

**Patient Profile:**
- Age: 35
- Gender: female
- Chief Complaint: Migraine follow-up
- Urgency: low

**Journey Steps:** 4

1. **Telehealth** - telehealth/consult
2. **Diagnosis** - tasks/sendSubscribe
3. **Pharmacy** - pharmacy/recommend
4. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~10 seconds

---

### 4. Telehealth Audio Only Followup

**Description:** Audio-only telehealth follow-up with escalation guardrails.

**Patient Profile:**
- Age: 73
- Gender: male
- Chief Complaint: Medication side-effect review
- Urgency: low

**Journey Steps:** 4

1. **Telehealth** - telehealth/consult
2. **Primary Care** - primary_care/manage_visit
3. **Pharmacy** - pharmacy/check_interactions
4. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~9 seconds

---

### 5. Home Visit House Call

**Description:** Home-based primary care visit including environment and safety assessment.

**Patient Profile:**
- Age: 84
- Gender: female
- Chief Complaint: Frailty and recurrent falls
- Urgency: medium

**Journey Steps:** 4

1. **Home Visit** - home_visit/dispatch
2. **Primary Care** - primary_care/manage_visit
3. **Pharmacy** - pharmacy/recommend
4. **Coordinator** - tasks/sendSubscribe

**Expected Duration:** ~15 seconds

---

### 6. Chronic Care Management Monthly

**Description:** Longitudinal CCM monthly cycle with care-plan update and coordination.

**Patient Profile:**
- Age: 69
- Gender: male
- Chief Complaint: CCM monthly review for diabetes and CHF
- Urgency: low

**Journey Steps:** 4

1. **Ccm** - ccm/monthly_review
2. **Primary Care** - primary_care/manage_visit
3. **Followup** - tasks/sendSubscribe
4. **Pharmacy** - pharmacy/check_interactions

**Expected Duration:** ~11 seconds

---

### 7. Emergency Department Treat And Release

**Description:** ED flow resulting in treatment and safe discharge.

**Patient Profile:**
- Age: 29
- Gender: male
- Chief Complaint: Acute asthma exacerbation
- Urgency: high

**Journey Steps:** 6

1. **Triage** - tasks/sendSubscribe
2. **Diagnosis** - tasks/sendSubscribe
3. **Imaging** - tasks/sendSubscribe
4. **Pharmacy** - tasks/sendSubscribe
5. **Discharge** - tasks/sendSubscribe
6. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~16 seconds

---

### 8. Emergency Department To Inpatient Admission

**Description:** ED flow that escalates to inpatient admission.

**Patient Profile:**
- Age: 57
- Gender: female
- Chief Complaint: Chest pain and diaphoresis
- Urgency: critical

**Journey Steps:** 5

1. **Triage** - tasks/sendSubscribe
2. **Diagnosis** - tasks/sendSubscribe
3. **Imaging** - tasks/sendSubscribe
4. **Bed Manager** - tasks/sendSubscribe
5. **Coordinator** - tasks/sendSubscribe

**Expected Duration:** ~14 seconds

---

### 9. Inpatient Admission And Daily Rounds

**Description:** Inpatient episode focusing on admission, medication safety, and daily review.

**Patient Profile:**
- Age: 72
- Gender: male
- Chief Complaint: Community acquired pneumonia with hypoxia
- Urgency: high

**Journey Steps:** 4

1. **Bed Manager** - admission/assign_bed
2. **Pharmacy** - tasks/sendSubscribe
3. **Coordinator** - tasks/sendSubscribe
4. **Ccm** - ccm/monthly_review

**Expected Duration:** ~12 seconds

---

### 10. Inpatient Discharge Transition

**Description:** Discharge and transition-of-care workflow to outpatient follow-up.

**Patient Profile:**
- Age: 66
- Gender: female
- Chief Complaint: Discharge readiness after CHF admission
- Urgency: medium

**Journey Steps:** 4

1. **Discharge** - tasks/sendSubscribe
2. **Pharmacy** - pharmacy/recommend
3. **Followup** - tasks/sendSubscribe
4. **Ccm** - ccm/monthly_review

**Expected Duration:** ~11 seconds

---

### 11. Chest Pain Cardiac

**Description:** Adult with severe chest pain and suspected acute coronary syndrome.

**Patient Profile:**
- Age: 55
- Gender: male
- Chief Complaint: Severe chest pain with dyspnea
- Urgency: high

**Journey Steps:** 5

1. **Triage** - tasks/sendSubscribe
2. **Diagnosis** - tasks/sendSubscribe
3. **Imaging** - tasks/sendSubscribe
4. **Pharmacy** - tasks/sendSubscribe
5. **Bed Manager** - tasks/sendSubscribe

**Expected Duration:** ~18 seconds

---

### 12. Pediatric Fever Sepsis

**Description:** Child with high fever and lethargy requiring sepsis workup.

**Patient Profile:**
- Age: 3
- Gender: female
- Chief Complaint: High fever and poor feeding
- Urgency: high

**Journey Steps:** 4

1. **Triage** - tasks/sendSubscribe
2. **Diagnosis** - tasks/sendSubscribe
3. **Pharmacy** - tasks/sendSubscribe
4. **Bed Manager** - tasks/sendSubscribe

**Expected Duration:** ~14 seconds

---

### 13. Orthopedic Fracture

**Description:** Extremity fracture workflow with imaging, pain control, and follow-up.

**Patient Profile:**
- Age: 28
- Gender: male
- Chief Complaint: Left leg pain after fall
- Urgency: medium

**Journey Steps:** 5

1. **Triage** - tasks/sendSubscribe
2. **Diagnosis** - tasks/sendSubscribe
3. **Imaging** - tasks/sendSubscribe
4. **Discharge** - tasks/sendSubscribe
5. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~12 seconds

---

### 14. Geriatric Confusion

**Description:** Elderly patient with acute confusion and delirium-focused pathway.

**Patient Profile:**
- Age: 78
- Gender: female
- Chief Complaint: Sudden confusion and agitation
- Urgency: high

**Journey Steps:** 4

1. **Triage** - tasks/sendSubscribe
2. **Diagnosis** - tasks/sendSubscribe
3. **Imaging** - tasks/sendSubscribe
4. **Bed Manager** - tasks/sendSubscribe

**Expected Duration:** ~13 seconds

---

### 15. Obstetric Emergency

**Description:** Pregnancy bleeding emergency with urgent maternal/fetal coordination.

**Patient Profile:**
- Age: 32
- Gender: female
- Chief Complaint: Bleeding at 28 weeks gestation
- Urgency: critical

**Journey Steps:** 4

1. **Triage** - tasks/sendSubscribe
2. **Diagnosis** - tasks/sendSubscribe
3. **Imaging** - tasks/sendSubscribe
4. **Bed Manager** - tasks/sendSubscribe

**Expected Duration:** ~12 seconds

---

### 16. Mental Health Crisis

**Description:** Acute psychiatric crisis with safety and inpatient behavioral health planning.

**Patient Profile:**
- Age: 35
- Gender: male
- Chief Complaint: Suicidal thoughts
- Urgency: critical

**Journey Steps:** 3

1. **Triage** - tasks/sendSubscribe
2. **Diagnosis** - tasks/sendSubscribe
3. **Bed Manager** - tasks/sendSubscribe

**Expected Duration:** ~10 seconds

---

### 17. Chronic Diabetes Complication

**Description:** Diabetic foot complication needing multidisciplinary inpatient planning.

**Patient Profile:**
- Age: 62
- Gender: female
- Chief Complaint: Foot ulcer with infection
- Urgency: medium

**Journey Steps:** 4

1. **Diagnosis** - tasks/sendSubscribe
2. **Imaging** - tasks/sendSubscribe
3. **Pharmacy** - tasks/sendSubscribe
4. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~12 seconds

---

### 18. Trauma Motor Vehicle Accident

**Description:** Polytrauma workflow from high-speed MVC.

**Patient Profile:**
- Age: 25
- Gender: male
- Chief Complaint: Multiple traumatic injuries
- Urgency: critical

**Journey Steps:** 4

1. **Triage** - tasks/sendSubscribe
2. **Diagnosis** - tasks/sendSubscribe
3. **Imaging** - tasks/sendSubscribe
4. **Bed Manager** - tasks/sendSubscribe

**Expected Duration:** ~13 seconds

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

**Journey Steps:** 4

1. **Triage** - tasks/sendSubscribe
2. **Diagnosis** - tasks/sendSubscribe
3. **Pharmacy** - tasks/sendSubscribe
4. **Followup** - tasks/sendSubscribe

**Expected Duration:** ~11 seconds

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

### 24. Notifiable Outbreak Public Health Loop

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

## Agent Coverage

The following agents are exercised across all scenarios:

- **Bed Manager**
- **Ccm**
- **Central Surveillance**
- **Consent Analyser**
- **Coordinator**
- **Diagnosis**
- **Discharge**
- **Ehr Writer**
- **Followup**
- **Hitl Ui**
- **Home Visit**
- **Hospital Reporter**
- **Imaging**
- **Insurer Agent**
- **Openhie Mediator**
- **Osint Agent**
- **Pharmacy**
- **Primary Care**
- **Provider Agent**
- **Specialty Care**
- **Summariser**
- **Telehealth**
- **Transcriber**
- **Triage**

**Total Agents:** 24
