# HelixCare Patient Journey Scenarios

Generated: 2024-01-15 12:00:00

Total Scenarios: 5

## Scenario Overview

### 1. chest_pain_cardiac
**Description:** Adult male with chest pain - suspected cardiac event

**Patient Profile:**
- Age: 55
- Gender: male
- Chief Complaint: Severe chest pain, shortness of breath
- Urgency: high

**Journey Steps:** 8

1. **triage** - tasks/sendSubscribe
2. **diagnosis** - tasks/sendSubscribe
3. **imaging** - tasks/sendSubscribe
4. **pharmacy** - tasks/sendSubscribe
5. **bed_manager** - tasks/sendSubscribe
6. **coordinator** - tasks/sendSubscribe
7. **discharge** - tasks/sendSubscribe
8. **followup** - tasks/sendSubscribe

**Expected Duration:** ~25 seconds

---

### 2. pediatric_fever_sepsis
**Description:** Child with high fever - suspected sepsis workup

**Patient Profile:**
- Age: 3
- Gender: female
- Chief Complaint: High fever, lethargy, poor feeding
- Urgency: high

**Journey Steps:** 6

1. **triage** - tasks/sendSubscribe
2. **diagnosis** - tasks/sendSubscribe
3. **imaging** - tasks/sendSubscribe
4. **pharmacy** - tasks/sendSubscribe
5. **bed_manager** - tasks/sendSubscribe
6. **coordinator** - tasks/sendSubscribe

**Expected Duration:** ~18 seconds

---

### 3. orthopedic_fracture
**Description:** Adult with extremity fracture - orthopedic evaluation

**Patient Profile:**
- Age: 28
- Gender: male
- Chief Complaint: Left leg pain after fall
- Urgency: medium

**Journey Steps:** 8

1. **triage** - tasks/sendSubscribe
2. **diagnosis** - tasks/sendSubscribe
3. **imaging** - tasks/sendSubscribe
4. **pharmacy** - tasks/sendSubscribe
5. **bed_manager** - tasks/sendSubscribe
6. **coordinator** - tasks/sendSubscribe
7. **discharge** - tasks/sendSubscribe
8. **followup** - tasks/sendSubscribe

**Expected Duration:** ~20 seconds

---

### 4. geriatric_confusion
**Description:** Elderly patient with acute confusion - delirium workup

**Patient Profile:**
- Age: 78
- Gender: female
- Chief Complaint: Sudden confusion and agitation
- Urgency: high

**Journey Steps:** 6

1. **triage** - tasks/sendSubscribe
2. **diagnosis** - tasks/sendSubscribe
3. **imaging** - tasks/sendSubscribe
4. **pharmacy** - tasks/sendSubscribe
5. **bed_manager** - tasks/sendSubscribe
6. **coordinator** - tasks/sendSubscribe

**Expected Duration:** ~22 seconds

---

### 5. obstetric_emergency
**Description:** Pregnant patient with vaginal bleeding - obstetric emergency

**Patient Profile:**
- Age: 32
- Gender: female
- Chief Complaint: Vaginal bleeding in pregnancy
- Urgency: critical

**Journey Steps:** 6

1. **triage** - tasks/sendSubscribe
2. **diagnosis** - tasks/sendSubscribe
3. **imaging** - tasks/sendSubscribe
4. **pharmacy** - tasks/sendSubscribe
5. **bed_manager** - tasks/sendSubscribe
6. **coordinator** - tasks/sendSubscribe

**Expected Duration:** ~18 seconds

---

## Agent Coverage

The following agents are exercised across all scenarios:

- **triage**
- **diagnosis**
- **imaging**
- **pharmacy**
- **bed_manager**
- **coordinator**
- **discharge**
- **followup**

**Total Agents:** 8