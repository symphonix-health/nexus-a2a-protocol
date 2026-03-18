"""Generate 100 use-case-mapped test scenarios (85 positive, 10 negative, 5 edge).

Each scenario maps to a specific use case ID from use_cases.json and tests
the deviation register alongside the personalisation engine.
"""

import json
from pathlib import Path

SCENARIOS_DIR = Path(__file__).parent / "scenarios"


def _make_scenario(
    usecaseid: str,
    component: str,
    scenario: str,
    testtype: str,
    priority: str,
    pathway_id: str,
    patient_context: dict,
    expected_status: str,
    expected_modifications: list[str],
    expected_safety_alerts: list[str],
    pre_conditions: str,
    post_conditions: str,
    compliance_tags: str,
    notes: str,
    use_case_ref: str = "",
    expected_deviation_count: int | None = None,
    expected_deviation_severities: list[str] | None = None,
    expected_requires_signoff: bool | None = None,
) -> dict:
    input_data = {
        "pathway_id": pathway_id,
        "patient_context": patient_context,
    }
    expected_outcome = {
        "status": expected_status,
        "modifications": expected_modifications,
        "safety_alerts": expected_safety_alerts,
    }
    if expected_deviation_count is not None:
        expected_outcome["deviation_count"] = expected_deviation_count
    if expected_deviation_severities is not None:
        expected_outcome["deviation_severities"] = expected_deviation_severities
    if expected_requires_signoff is not None:
        expected_outcome["requires_clinician_signoff"] = expected_requires_signoff

    return {
        "usecaseid": usecaseid,
        "component": component,
        "scenario": scenario,
        "testtype": testtype,
        "priority": priority,
        "inputdata": json.dumps(input_data),
        "expectedoutcome": expected_outcome,
        "pre_conditions": pre_conditions,
        "post_conditions": post_conditions,
        "dependencies": "clinical-pathways engine",
        "performancemetrics": "response_time < 500ms",
        "securitycontext": "PHI redacted for AI processing",
        "compliancetags": compliance_tags,
        "notes": notes,
        "requestresponsejourney": {
            "request": {
                "fields_required": ["pathway_id", "patient_context"],
                "example_payload": input_data,
            },
            "response": {
                "expected_fields": [
                    "personalised_pathway",
                    "explainability_report",
                    "modifications",
                    "deviation_register",
                    "confidence_level",
                    "safety_alerts",
                ],
                "validation_checks": [f"Outcome is {expected_status}"],
            },
            "journey_steps": [
                "1. Patient context assembled",
                "2. Pathway loaded from repository",
                "3. Personalisation rules evaluated",
                "4. Safety guardrails checked",
                "5. Deviation register built",
                "6. Personalised pathway built",
                "7. Audit trail recorded",
            ],
        },
        "operationtype": "personalise",
        "use_case_ref": use_case_ref,
    }


def _simple_patient(pid, age, gender, **kwargs):
    ctx = {
        "demographics": {"patient_id": pid, "age": age, "gender": gender},
        "chief_complaint": kwargs.get("chief_complaint", ""),
        "conditions": kwargs.get("conditions", []),
        "medications": kwargs.get("medications", []),
        "allergies": kwargs.get("allergies", []),
        "observations": kwargs.get("observations", []),
        "vital_signs": kwargs.get("vital_signs", {}),
        "frailty_score": kwargs.get("frailty_score", ""),
        "social_history": kwargs.get("social_history", {}),
        "encounters": kwargs.get("encounters", []),
    }
    return ctx


def generate() -> list[dict]:
    scenarios = []
    idx = 0

    def _id(prefix, testtype):
        nonlocal idx
        idx += 1
        return f"{prefix}-{testtype[:3].upper()}-{idx:03d}"

    # ════════════════════════════════════════════════════════════════
    # UC-01: Personalised Encounter Journey (standard, no modifications)
    # ════════════════════════════════════════════════════════════════

    for i, (age, gender, pathway) in enumerate([
        (45, "female", "nice-ng106-heart-failure"),
        (52, "male", "nice-ng115-copd"),
        (48, "female", "nice-ng28-diabetes-type2"),
        (33, "male", "nice-ng51-sepsis"),
        (28, "female", "who-maternal-anc"),
        (55, "male", "nice-ng106-heart-failure"),
        (61, "female", "nice-ng115-copd"),
    ]):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC01", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-01: Standard encounter journey — {pathway.split('-')[-1]} (age {age})",
            testtype="Positive", priority="P1",
            pathway_id=pathway,
            patient_context=_simple_patient(f"UC01-{i}", age, gender, chief_complaint="assessment"),
            expected_status="personalised_pathway_returned",
            expected_modifications=[], expected_safety_alerts=[],
            pre_conditions=f"Pathway {pathway} loaded in repository",
            post_conditions="Personalised pathway returned with no deviations and audit trail",
            compliance_tags="NICE,GDPR,Caldicott",
            notes="Standard pathway, no individualisation needed",
            use_case_ref="UC-01",
            expected_deviation_count=0,
        ))

    # ════════════════════════════════════════════════════════════════
    # UC-02: Multi-morbidity Pathway Reconciliation
    # ════════════════════════════════════════════════════════════════

    # HF + CKD
    for i, egfr in enumerate([25, 28, 18, 22, 35]):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC02", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-02: HF + CKD (eGFR={egfr}) multimorbidity reconciliation",
            testtype="Positive", priority="P0",
            pathway_id="nice-ng106-heart-failure",
            patient_context=_simple_patient(
                f"UC02-HF-{i}", 68, "male",
                conditions=[
                    {"code": "heart_failure", "display": "Heart failure"},
                    {"code": "ckd_stage_4", "display": "CKD Stage 4"},
                ],
                observations=[{"code": "egfr", "value": egfr, "unit": "mL/min/1.73m2"}],
                chief_complaint="breathlessness",
            ),
            expected_status="personalised_pathway_returned",
            expected_modifications=["sequence_changed", "urgency_elevated"] + (["contraindication_flagged"] if egfr < 30 else []),
            expected_safety_alerts=[],
            pre_conditions="Pathway nice-ng106-heart-failure loaded",
            post_conditions="Reconciled pathway with CKD-safe modifications and deviation register",
            compliance_tags="NICE,GDPR,Caldicott",
            notes=f"Tests HF+CKD reconciliation with eGFR={egfr}",
            use_case_ref="UC-02",
            expected_requires_signoff=egfr < 30,
        ))

    # COPD + CHF
    for i in range(3):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC02", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-02: COPD + CHF comorbidity reconciliation (variant {i+1})",
            testtype="Positive", priority="P0",
            pathway_id="nice-ng115-copd",
            patient_context=_simple_patient(
                f"UC02-COPD-{i}", 70 + i, "male",
                conditions=[
                    {"code": "copd", "display": "COPD"},
                    {"code": "heart_failure", "display": "Heart failure"},
                ],
                chief_complaint="breathlessness",
            ),
            expected_status="personalised_pathway_returned",
            expected_modifications=["safety_override", "urgency_elevated"],
            expected_safety_alerts=[],
            pre_conditions="Pathway nice-ng115-copd loaded",
            post_conditions="Joint respiratory-cardiology referral added with deviation register",
            compliance_tags="NICE,GDPR,Caldicott",
            notes="Tests COPD+CHF comorbidity handling",
            use_case_ref="UC-02",
            expected_requires_signoff=True,
        ))

    # ════════════════════════════════════════════════════════════════
    # UC-03: Safety Guardrail Enforcement
    # ════════════════════════════════════════════════════════════════

    # Critical potassium
    for i, k in enumerate([6.2, 6.5, 2.8, 2.5]):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC03", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-03: Critical potassium K+={k} safety guardrail",
            testtype="Positive", priority="P0",
            pathway_id="nice-ng106-heart-failure",
            patient_context=_simple_patient(
                f"UC03-K-{i}", 65, "male",
                conditions=[{"code": "heart_failure", "display": "HF"}],
                observations=[{"code": "potassium", "value": k, "unit": "mmol/L"}],
            ),
            expected_status="personalised_pathway_returned",
            expected_modifications=["safety_override"],
            expected_safety_alerts=[],
            pre_conditions="Pathway loaded",
            post_conditions="Safety override documented in deviation register with critical severity",
            compliance_tags="NICE,GDPR,Caldicott",
            notes=f"Critical potassium {k} triggers safety guardrail",
            use_case_ref="UC-03",
            expected_deviation_severities=["critical"],
            expected_requires_signoff=True,
        ))

    # Drug interaction — triple whammy
    scenarios.append(_make_scenario(
        usecaseid=_id("UC03", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-03: Triple whammy drug interaction (ACEi + MRA + NSAID)",
        testtype="Positive", priority="P0",
        pathway_id="nice-ng106-heart-failure",
        patient_context=_simple_patient(
            "UC03-TRIPLE", 72, "male",
            conditions=[{"code": "heart_failure", "display": "HF"}],
            medications=[
                {"code": "ramipril", "display": "Ramipril"},
                {"code": "spironolactone", "display": "Spironolactone"},
                {"code": "ibuprofen", "display": "Ibuprofen"},
            ],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["safety_override"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Triple whammy flagged with critical deviation",
        compliance_tags="NICE,GDPR,Caldicott,BNF",
        notes="ACEi+MRA+NSAID triple whammy detection",
        use_case_ref="UC-03",
        expected_requires_signoff=True,
    ))

    # Metformin + eGFR < 30
    scenarios.append(_make_scenario(
        usecaseid=_id("UC03", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-03: Metformin contraindication eGFR=18 safety guardrail",
        testtype="Positive", priority="P0",
        pathway_id="nice-ng28-diabetes-type2",
        patient_context=_simple_patient(
            "UC03-MET", 62, "female",
            conditions=[{"code": "type_2_diabetes", "display": "T2DM"}],
            medications=[{"code": "metformin", "display": "Metformin"}],
            observations=[{"code": "egfr", "value": 18, "unit": "mL/min/1.73m2"}],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["contraindication_flagged"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Metformin contraindication in deviation register",
        compliance_tags="NICE,GDPR,BNF",
        notes="Metformin + severe renal impairment",
        use_case_ref="UC-03",
        expected_requires_signoff=True,
    ))

    # ════════════════════════════════════════════════════════════════
    # UC-04: Urgency Escalation
    # ════════════════════════════════════════════════════════════════

    # Sepsis with high lactate
    for i, lactate in enumerate([4.5, 5.2, 6.0]):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC04", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-04: Sepsis urgency escalation lactate={lactate}",
            testtype="Positive", priority="P0",
            pathway_id="nice-ng51-sepsis",
            patient_context=_simple_patient(
                f"UC04-SEP-{i}", 55 + i*5, "male",
                conditions=[{"code": "urinary_tract_infection", "display": "UTI"}],
                observations=[{"code": "lactate", "value": lactate, "unit": "mmol/L"}],
                vital_signs={"heart_rate": 115, "systolic_bp": 82, "temperature": 39.1},
            ),
            expected_status="personalised_pathway_returned",
            expected_modifications=["urgency_elevated"],
            expected_safety_alerts=[],
            pre_conditions="Pathway loaded",
            post_conditions="Urgency elevated with deviation documented",
            compliance_tags="NICE,GDPR",
            notes=f"Sepsis with lactate {lactate} triggers escalation",
            use_case_ref="UC-04",
        ))

    # DM foot ulcer urgency
    scenarios.append(_make_scenario(
        usecaseid=_id("UC04", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-04: Diabetic foot ulcer urgency escalation HbA1c=85",
        testtype="Positive", priority="P0",
        pathway_id="nice-ng28-diabetes-type2",
        patient_context=_simple_patient(
            "UC04-FOOT", 58, "male",
            conditions=[
                {"code": "type_2_diabetes", "display": "T2DM"},
                {"code": "diabetic_foot_ulcer", "display": "Active foot ulcer"},
            ],
            observations=[{"code": "hba1c", "value": 85, "unit": "mmol/mol"}],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["activity_added", "urgency_elevated", "intensity_increased"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="MDT referral and urgency elevation in deviation register",
        compliance_tags="NICE,GDPR",
        notes="Active foot ulcer + high HbA1c triggers multiple escalations",
        use_case_ref="UC-04",
    ))

    # ════════════════════════════════════════════════════════════════
    # UC-05: Specialist Referral Routing
    # ════════════════════════════════════════════════════════════════

    for i, (pathway, conditions, obs, expected_mods) in enumerate([
        ("nice-ng106-heart-failure",
         [{"code": "heart_failure"}, {"code": "ckd_stage_3"}],
         [{"code": "egfr", "value": 28, "unit": "mL/min/1.73m2"}],
         ["urgency_elevated"]),  # HF+CKD → expedited cardiology referral
        ("nice-ng28-diabetes-type2",
         [{"code": "type_2_diabetes"}, {"code": "ckd_stage_4"}],
         [{"code": "egfr", "value": 22, "unit": "mL/min/1.73m2"}],
         ["activity_added"]),  # DM+CKD → specialist renal-diabetes referral
        ("nice-ng28-diabetes-type2",
         [{"code": "type_2_diabetes"}, {"code": "diabetic_foot_ulcer"}],
         [{"code": "hba1c", "value": 78, "unit": "mmol/mol"}],
         ["activity_added"]),  # Foot ulcer → MDT referral
    ]):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC05", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-05: Specialist referral routing — {pathway.split('-')[-1]} (variant {i+1})",
            testtype="Positive", priority="P1",
            pathway_id=pathway,
            patient_context=_simple_patient(
                f"UC05-{i}", 63 + i, "male",
                conditions=conditions, observations=obs,
            ),
            expected_status="personalised_pathway_returned",
            expected_modifications=expected_mods,
            expected_safety_alerts=[],
            pre_conditions="Pathway loaded",
            post_conditions="Specialist referral added and documented in deviation register",
            compliance_tags="NICE,GDPR",
            notes="Specialist referral added based on comorbidity pattern",
            use_case_ref="UC-05",
        ))

    # ════════════════════════════════════════════════════════════════
    # UC-06: Contraindication-Driven Medication Adjustment
    # ════════════════════════════════════════════════════════════════

    for i, (pathway, meds, egfr) in enumerate([
        ("nice-ng28-diabetes-type2", [{"code": "metformin"}], 24),
        ("nice-ng28-diabetes-type2", [{"code": "metformin"}], 19),
        ("nice-ng106-heart-failure",
         [{"code": "ramipril"}, {"code": "spironolactone"}],
         25),
    ]):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC06", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-06: Medication contraindication eGFR={egfr} ({pathway.split('-')[-1]})",
            testtype="Positive", priority="P0",
            pathway_id=pathway,
            patient_context=_simple_patient(
                f"UC06-{i}", 60 + i, "male",
                conditions=[{"code": "type_2_diabetes" if "diabetes" in pathway else "heart_failure"}]
                + [{"code": "ckd_stage_4"}],
                medications=meds,
                observations=[{"code": "egfr", "value": egfr, "unit": "mL/min/1.73m2"}],
            ),
            expected_status="personalised_pathway_returned",
            expected_modifications=["contraindication_flagged"],
            expected_safety_alerts=[],
            pre_conditions="Pathway loaded",
            post_conditions="Contraindication documented in deviation register with major severity",
            compliance_tags="NICE,GDPR,BNF",
            notes=f"Medication contraindication at eGFR={egfr}",
            use_case_ref="UC-06",
            expected_requires_signoff=True,
        ))

    # Penicillin allergy in sepsis
    scenarios.append(_make_scenario(
        usecaseid=_id("UC06", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-06: Penicillin allergy — alternative antimicrobial in sepsis",
        testtype="Positive", priority="P0",
        pathway_id="nice-ng51-sepsis",
        patient_context=_simple_patient(
            "UC06-PEN", 55, "female",
            conditions=[{"code": "pneumonia", "display": "Community-acquired pneumonia"}],
            allergies=[{"substance": "penicillin", "category": "medication", "reaction": "anaphylaxis", "severity": "severe"}],
            vital_signs={"heart_rate": 105, "temperature": 38.8},
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["contraindication_flagged"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Alternative antimicrobial regimen documented in deviation register",
        compliance_tags="NICE,GDPR",
        notes="Penicillin allergy triggers alternative antimicrobial",
        use_case_ref="UC-06",
        expected_requires_signoff=True,
    ))

    # ════════════════════════════════════════════════════════════════
    # UC-07: Monitoring Schedule Personalisation
    # ════════════════════════════════════════════════════════════════

    # Frailty adaptation
    for i, frailty in enumerate(["moderate", "severe"]):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC07", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-07: Frailty-adapted monitoring ({frailty})",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng106-heart-failure",
            patient_context=_simple_patient(
                f"UC07-FR-{i}", 78 + i, "female",
                conditions=[{"code": "heart_failure"}],
                frailty_score=frailty,
            ),
            expected_status="personalised_pathway_returned",
            expected_modifications=["follow_up_adapted"] + (["intensity_reduced"] if frailty == "severe" else []),
            expected_safety_alerts=[],
            pre_conditions="Pathway loaded",
            post_conditions="Follow-up adapted to community-based monitoring",
            compliance_tags="NICE,GDPR",
            notes=f"Frailty {frailty} triggers monitoring adaptation",
            use_case_ref="UC-07",
        ))

    # Recurrent admissions
    scenarios.append(_make_scenario(
        usecaseid=_id("UC07", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-07: Recurrent admissions (3 in 12mo) — enhanced monitoring",
        testtype="Positive", priority="P1",
        pathway_id="nice-ng115-copd",
        patient_context=_simple_patient(
            "UC07-READM", 66, "male",
            conditions=[{"code": "copd"}],
            encounters=[
                {"encounter_id": "E1", "encounter_type": "inpatient", "date": "2026-01-10T00:00:00", "reason": "COPD exacerbation"},
                {"encounter_id": "E2", "encounter_type": "inpatient", "date": "2025-09-15T00:00:00", "reason": "COPD exacerbation"},
                {"encounter_id": "E3", "encounter_type": "emergency", "date": "2025-06-20T00:00:00", "reason": "Breathlessness"},
            ],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["intensity_increased"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Enhanced monitoring schedule in deviation register",
        compliance_tags="NICE,GDPR",
        notes="3 admissions triggers enhanced monitoring",
        use_case_ref="UC-07",
    ))

    # Transport barrier
    scenarios.append(_make_scenario(
        usecaseid=_id("UC07", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-07: Transport barrier — telehealth follow-up adaptation",
        testtype="Positive", priority="P1",
        pathway_id="nice-ng28-diabetes-type2",
        patient_context=_simple_patient(
            "UC07-TRANS", 55, "female",
            conditions=[{"code": "type_2_diabetes"}],
            social_history={"transport_access": "poor"},
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["follow_up_adapted"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Follow-up adapted to telehealth with deviation documented",
        compliance_tags="NICE,GDPR",
        notes="Poor transport access triggers telehealth adaptation",
        use_case_ref="UC-07",
    ))

    # ════════════════════════════════════════════════════════════════
    # UC-08: Polypharmacy Medication Review
    # ════════════════════════════════════════════════════════════════

    med_list_10 = [{"code": f"med{j}", "display": f"Medication {j}"} for j in range(10)]
    med_list_12 = [{"code": f"med{j}", "display": f"Medication {j}"} for j in range(12)]

    for i, (meds, pathway) in enumerate([
        (med_list_10, "nice-ng106-heart-failure"),
        (med_list_12, "nice-ng28-diabetes-type2"),
        (med_list_10, "nice-ng115-copd"),
    ]):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC08", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-08: Polypharmacy review ({len(meds)} meds) — {pathway.split('-')[-1]}",
            testtype="Positive", priority="P1",
            pathway_id=pathway,
            patient_context=_simple_patient(
                f"UC08-{i}", 70 + i, "male",
                conditions=[{"code": "heart_failure" if "heart" in pathway else "type_2_diabetes" if "diabetes" in pathway else "copd"}],
                medications=meds,
            ),
            expected_status="personalised_pathway_returned",
            expected_modifications=["sequence_changed"],
            expected_safety_alerts=[],
            pre_conditions="Pathway loaded",
            post_conditions="Medication review prioritised in deviation register",
            compliance_tags="NICE,GDPR",
            notes=f"Polypharmacy ({len(meds)} meds) triggers review prioritisation",
            use_case_ref="UC-08",
        ))

    # HF-specific polypharmacy (5+ meds)
    med_list_6 = [{"code": f"hfmed{j}", "display": f"HF Med {j}"} for j in range(6)]
    scenarios.append(_make_scenario(
        usecaseid=_id("UC08", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-08: HF polypharmacy review (6 meds, HF-specific threshold)",
        testtype="Positive", priority="P1",
        pathway_id="nice-ng106-heart-failure",
        patient_context=_simple_patient(
            "UC08-HF5", 68, "female",
            conditions=[{"code": "heart_failure"}],
            medications=med_list_6,
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["sequence_changed"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="HF-specific medication review prioritised",
        compliance_tags="NICE,GDPR",
        notes="HF polypharmacy threshold is 5 meds",
        use_case_ref="UC-08",
    ))

    # ════════════════════════════════════════════════════════════════
    # UC-09: Language and Social Barrier Adaptation
    # ════════════════════════════════════════════════════════════════

    for i, (lang_barrier, interpreter, pathway) in enumerate([
        (True, False, "nice-ng106-heart-failure"),
        (False, True, "nice-ng28-diabetes-type2"),
        (True, True, "nice-ng51-sepsis"),
    ]):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC09", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-09: Language barrier adaptation — {pathway.split('-')[-1]}",
            testtype="Positive", priority="P1",
            pathway_id=pathway,
            patient_context=_simple_patient(
                f"UC09-{i}", 50 + i*5, "female",
                conditions=[{"code": "heart_failure" if "heart" in pathway else "type_2_diabetes" if "diabetes" in pathway else "pneumonia"}],
                social_history={"language_barrier": lang_barrier, "interpreter_needed": interpreter},
            ),
            expected_status="personalised_pathway_returned",
            expected_modifications=["activity_added"],
            expected_safety_alerts=[],
            pre_conditions="Pathway loaded",
            post_conditions="Interpreter service added with deviation documented",
            compliance_tags="NICE,GDPR,Equality Act",
            notes="Language barrier triggers interpreter service",
            use_case_ref="UC-09",
        ))

    # ════════════════════════════════════════════════════════════════
    # UC-10: Maternal — Advanced Age Monitoring
    # ════════════════════════════════════════════════════════════════

    for i, age in enumerate([40, 42, 44]):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC10", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-10: Advanced maternal age ({age}) — enhanced ANC monitoring",
            testtype="Positive", priority="P1",
            pathway_id="who-maternal-anc",
            patient_context=_simple_patient(
                f"UC10-{i}", age, "female",
                conditions=[{"code": "pregnancy", "display": "Pregnancy"}],
                chief_complaint="antenatal booking",
            ),
            expected_status="personalised_pathway_returned",
            expected_modifications=["intensity_increased"],
            expected_safety_alerts=[],
            pre_conditions="Pathway loaded",
            post_conditions="Enhanced ANC monitoring in deviation register",
            compliance_tags="WHO,NICE,GDPR",
            notes=f"Maternal age {age} triggers enhanced monitoring",
            use_case_ref="UC-10",
        ))

    # ════════════════════════════════════════════════════════════════
    # UC-11: Maternal — Pre-eclampsia Prevention
    # ════════════════════════════════════════════════════════════════

    for i, age in enumerate([32, 38]):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC11", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-11: Pre-eclampsia history — aspirin + BP monitoring (age {age})",
            testtype="Positive", priority="P0",
            pathway_id="who-maternal-anc",
            patient_context=_simple_patient(
                f"UC11-{i}", age, "female",
                conditions=[
                    {"code": "pregnancy", "display": "Pregnancy"},
                    {"code": "pre_eclampsia", "display": "Previous pre-eclampsia"},
                ],
                chief_complaint="antenatal booking",
            ),
            expected_status="personalised_pathway_returned",
            expected_modifications=["activity_added", "intensity_increased"],
            expected_safety_alerts=[],
            pre_conditions="Pathway loaded",
            post_conditions="Aspirin prophylaxis and BP monitoring in deviation register",
            compliance_tags="NICE,WHO,GDPR",
            notes="Pre-eclampsia history triggers aspirin + enhanced BP monitoring",
            use_case_ref="UC-11",
        ))

    # ════════════════════════════════════════════════════════════════
    # UC-12: Sepsis — Immunocompromised Escalation
    # ════════════════════════════════════════════════════════════════

    for i, condition in enumerate(["immunocompromised", "chemotherapy", "hiv"]):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC12", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-12: Sepsis + {condition} — broader antimicrobial cover",
            testtype="Positive", priority="P0",
            pathway_id="nice-ng51-sepsis",
            patient_context=_simple_patient(
                f"UC12-{i}", 60 + i*3, "male",
                conditions=[
                    {"code": "pneumonia", "display": "Pneumonia"},
                    {"code": condition, "display": condition.replace("_", " ").title()},
                ],
                vital_signs={"heart_rate": 108, "temperature": 38.5},
            ),
            expected_status="personalised_pathway_returned",
            expected_modifications=["intensity_increased", "urgency_elevated"],
            expected_safety_alerts=[],
            pre_conditions="Pathway loaded",
            post_conditions="Broader coverage and lower red-flag threshold documented",
            compliance_tags="NICE,GDPR",
            notes=f"Immunocompromised ({condition}) triggers escalation",
            use_case_ref="UC-12",
        ))

    # ════════════════════════════════════════════════════════════════
    # UC-13: Sepsis — Allergy-Safe Antimicrobial
    # ════════════════════════════════════════════════════════════════

    for i, severity in enumerate(["moderate", "severe"]):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC13", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-13: Penicillin allergy ({severity}) — alternative antimicrobial",
            testtype="Positive", priority="P0",
            pathway_id="nice-ng51-sepsis",
            patient_context=_simple_patient(
                f"UC13-{i}", 52 + i*8, "female",
                conditions=[{"code": "cellulitis", "display": "Cellulitis"}],
                allergies=[{"substance": "penicillin", "category": "medication", "reaction": "rash" if severity == "moderate" else "anaphylaxis", "severity": severity}],
                vital_signs={"heart_rate": 100, "temperature": 38.2},
            ),
            expected_status="personalised_pathway_returned",
            expected_modifications=["contraindication_flagged"],
            expected_safety_alerts=[],
            pre_conditions="Pathway loaded",
            post_conditions="Alternative antimicrobial in deviation register",
            compliance_tags="NICE,GDPR",
            notes=f"Penicillin allergy ({severity}) triggers alternative regimen",
            use_case_ref="UC-13",
            expected_requires_signoff=True,
        ))

    # ════════════════════════════════════════════════════════════════
    # UC-14: Sepsis — HF Fluid Safety
    # ════════════════════════════════════════════════════════════════

    for i in range(2):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC14", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-14: Sepsis + HF — cautious fluid resuscitation (variant {i+1})",
            testtype="Positive", priority="P0",
            pathway_id="nice-ng51-sepsis",
            patient_context=_simple_patient(
                f"UC14-{i}", 70 + i*4, "male",
                conditions=[
                    {"code": "pneumonia", "display": "Pneumonia"},
                    {"code": "heart_failure", "display": "Heart failure"},
                ],
                vital_signs={"heart_rate": 112, "systolic_bp": 88, "temperature": 38.7},
            ),
            expected_status="personalised_pathway_returned",
            expected_modifications=["safety_override"],
            expected_safety_alerts=[],
            pre_conditions="Pathway loaded",
            post_conditions="Cautious fluid approach documented in deviation register",
            compliance_tags="NICE,GDPR",
            notes="Sepsis+HF triggers cautious fluid resuscitation",
            use_case_ref="UC-14",
            expected_requires_signoff=True,
        ))

    # ════════════════════════════════════════════════════════════════
    # UC-17: Deviation Register Documentation
    # ════════════════════════════════════════════════════════════════

    # Complex patient with multiple deviations
    scenarios.append(_make_scenario(
        usecaseid=_id("UC17", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-17: Complex patient — multiple deviations documented in register",
        testtype="Positive", priority="P0",
        pathway_id="nice-ng106-heart-failure",
        patient_context=_simple_patient(
            "UC17-COMPLEX", 75, "male",
            conditions=[
                {"code": "heart_failure", "display": "HF"},
                {"code": "ckd_stage_4", "display": "CKD4"},
            ],
            medications=[{"code": f"med{j}", "display": f"Med {j}"} for j in range(12)],
            observations=[{"code": "egfr", "value": 22, "unit": "mL/min/1.73m2"}],
            frailty_score="moderate",
            social_history={"transport_access": "poor"},
            encounters=[
                {"encounter_id": "E1", "encounter_type": "inpatient", "date": "2026-01-10T00:00:00", "reason": "HF"},
                {"encounter_id": "E2", "encounter_type": "inpatient", "date": "2025-09-15T00:00:00", "reason": "HF"},
            ],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=[
            "sequence_changed", "urgency_elevated", "contraindication_flagged",
            "follow_up_adapted", "intensity_increased",
        ],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Multiple deviations with standard vs individualised comparison",
        compliance_tags="NICE,GDPR,Caldicott",
        notes="Tests comprehensive deviation register with many modifications",
        use_case_ref="UC-17",
        expected_requires_signoff=True,
    ))

    # UC-18: COPD Frequent Exacerbator
    for i in range(2):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC18", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-18: COPD frequent exacerbator — enhanced management (variant {i+1})",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng115-copd",
            patient_context=_simple_patient(
                f"UC18-{i}", 64 + i*3, "male",
                conditions=[{"code": "copd"}],
                encounters=[
                    {"encounter_id": "E1", "encounter_type": "inpatient", "date": "2026-02-01T00:00:00", "reason": "COPD exacerbation"},
                    {"encounter_id": "E2", "encounter_type": "inpatient", "date": "2025-10-01T00:00:00", "reason": "COPD exacerbation"},
                ],
            ),
            expected_status="personalised_pathway_returned",
            expected_modifications=["intensity_increased", "activity_added"],
            expected_safety_alerts=[],
            pre_conditions="Pathway loaded",
            post_conditions="Enhanced management and self-management plan in deviation register",
            compliance_tags="NICE,GDPR",
            notes="2+ admissions triggers frequent exacerbator pathway",
            use_case_ref="UC-18",
        ))

    # ════════════════════════════════════════════════════════════════
    # ADDITIONAL POSITIVE SCENARIOS — fill to 85 positive
    # ════════════════════════════════════════════════════════════════

    # UC-01 additional: more standard pathway variations
    for i, (age, gender, pathway) in enumerate([
        (38, "male", "nice-ng106-heart-failure"),
        (29, "female", "who-maternal-anc"),
        (50, "male", "nice-ng51-sepsis"),
        (44, "female", "nice-ng28-diabetes-type2"),
        (57, "male", "nice-ng115-copd"),
    ], start=10):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC01", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-01: Standard pathway — {pathway.split('-')[-1]} (age {age}, {gender})",
            testtype="Positive", priority="P1",
            pathway_id=pathway,
            patient_context=_simple_patient(f"UC01-EXT-{i}", age, gender, chief_complaint="assessment"),
            expected_status="personalised_pathway_returned",
            expected_modifications=[], expected_safety_alerts=[],
            pre_conditions=f"Pathway {pathway} loaded",
            post_conditions="No deviations — standard pathway",
            compliance_tags="NICE,GDPR",
            notes="Standard pathway, no individualisation",
            use_case_ref="UC-01",
            expected_deviation_count=0,
        ))

    # UC-02 additional: DM + CKD cross-pathway
    for i, egfr in enumerate([26, 20]):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC02", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-02: T2DM + CKD (eGFR={egfr}) multimorbidity reconciliation",
            testtype="Positive", priority="P0",
            pathway_id="nice-ng28-diabetes-type2",
            patient_context=_simple_patient(
                f"UC02-DM-EXT-{i}", 64, "female",
                conditions=[
                    {"code": "type_2_diabetes", "display": "T2DM"},
                    {"code": "ckd_stage_4", "display": "CKD4"},
                ],
                medications=[{"code": "metformin", "display": "Metformin"}],
                observations=[{"code": "egfr", "value": egfr, "unit": "mL/min/1.73m2"}],
            ),
            expected_status="personalised_pathway_returned",
            expected_modifications=["contraindication_flagged", "activity_added"],
            expected_safety_alerts=[],
            pre_conditions="Pathway loaded",
            post_conditions="Metformin contraindicated, renal-diabetes referral added",
            compliance_tags="NICE,GDPR",
            notes=f"DM+CKD reconciliation at eGFR={egfr}",
            use_case_ref="UC-02",
            expected_requires_signoff=True,
        ))

    # UC-03 additional: eGFR < 15 critical safety
    scenarios.append(_make_scenario(
        usecaseid=_id("UC03", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-03: Critical eGFR=12 — nephrology review safety guardrail",
        testtype="Positive", priority="P0",
        pathway_id="nice-ng106-heart-failure",
        patient_context=_simple_patient(
            "UC03-EGFR-CRIT", 72, "male",
            conditions=[{"code": "heart_failure"}, {"code": "ckd_stage_5"}],
            observations=[{"code": "egfr", "value": 12, "unit": "mL/min/1.73m2"}],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["safety_override"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Critical eGFR safety override in deviation register",
        compliance_tags="NICE,GDPR",
        notes="eGFR < 15 triggers critical safety guardrail",
        use_case_ref="UC-03",
        expected_requires_signoff=True,
    ))

    # UC-04 additional: immunocompromised urgency in sepsis
    scenarios.append(_make_scenario(
        usecaseid=_id("UC04", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-04: Sepsis + organ transplant — urgency escalation",
        testtype="Positive", priority="P0",
        pathway_id="nice-ng51-sepsis",
        patient_context=_simple_patient(
            "UC04-TRANSPLANT", 58, "male",
            conditions=[
                {"code": "pneumonia", "display": "Pneumonia"},
                {"code": "organ_transplant", "display": "Renal transplant"},
            ],
            vital_signs={"heart_rate": 102, "temperature": 38.3},
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["intensity_increased", "urgency_elevated"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Immunocompromised escalation documented",
        compliance_tags="NICE,GDPR",
        notes="Organ transplant triggers immunocompromised rule",
        use_case_ref="UC-04",
    ))

    # UC-05 additional: COPD + CHF joint referral
    scenarios.append(_make_scenario(
        usecaseid=_id("UC05", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-05: COPD + CHF — joint respiratory-cardiology referral",
        testtype="Positive", priority="P1",
        pathway_id="nice-ng115-copd",
        patient_context=_simple_patient(
            "UC05-JOINT", 69, "female",
            conditions=[{"code": "copd"}, {"code": "heart_failure"}],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["urgency_elevated"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Joint referral added in deviation register",
        compliance_tags="NICE,GDPR",
        notes="COPD+CHF triggers joint referral",
        use_case_ref="UC-05",
    ))

    # UC-07 additional: very severe frailty
    scenarios.append(_make_scenario(
        usecaseid=_id("UC07", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-07: Very severe frailty — goals of care discussion",
        testtype="Positive", priority="P1",
        pathway_id="nice-ng28-diabetes-type2",
        patient_context=_simple_patient(
            "UC07-VSFR", 85, "female",
            conditions=[{"code": "type_2_diabetes"}],
            frailty_score="very_severe",
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["follow_up_adapted", "intensity_reduced"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Goals of care and reduced intensity in deviation register",
        compliance_tags="NICE,GDPR",
        notes="Very severe frailty triggers intensity reduction + community follow-up",
        use_case_ref="UC-07",
    ))

    # UC-09 additional: transport barrier variants
    scenarios.append(_make_scenario(
        usecaseid=_id("UC09", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-09: Transport barrier + frailty — combined social adaptation",
        testtype="Positive", priority="P1",
        pathway_id="nice-ng115-copd",
        patient_context=_simple_patient(
            "UC09-COMBO", 76, "male",
            conditions=[{"code": "copd"}],
            frailty_score="moderate",
            social_history={"transport_access": "none"},
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["follow_up_adapted"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Telehealth + community follow-up in deviation register",
        compliance_tags="NICE,GDPR",
        notes="Transport + frailty combo triggers double adaptation",
        use_case_ref="UC-09",
    ))

    # UC-10 additional: maternal age variants
    for i, age in enumerate([41, 45]):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC10", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-10: Advanced maternal age ({age}) — enhanced monitoring variant {i+4}",
            testtype="Positive", priority="P1",
            pathway_id="who-maternal-anc",
            patient_context=_simple_patient(
                f"UC10-EXT-{i}", age, "female",
                conditions=[{"code": "pregnancy"}],
            ),
            expected_status="personalised_pathway_returned",
            expected_modifications=["intensity_increased"],
            expected_safety_alerts=[],
            pre_conditions="Pathway loaded",
            post_conditions="Enhanced ANC monitoring",
            compliance_tags="WHO,NICE,GDPR",
            notes=f"AMA at age {age}",
            use_case_ref="UC-10",
        ))

    # UC-11 additional: pre-eclampsia + AMA combined
    scenarios.append(_make_scenario(
        usecaseid=_id("UC11", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-11: Pre-eclampsia + AMA (42) — aspirin + enhanced monitoring",
        testtype="Positive", priority="P0",
        pathway_id="who-maternal-anc",
        patient_context=_simple_patient(
            "UC11-AMA-PE", 42, "female",
            conditions=[
                {"code": "pregnancy"},
                {"code": "pre_eclampsia", "display": "Previous pre-eclampsia"},
            ],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["activity_added", "intensity_increased"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Aspirin + AMA + BP monitoring deviations",
        compliance_tags="NICE,WHO,GDPR",
        notes="Combined pre-eclampsia + AMA triggers multiple deviations",
        use_case_ref="UC-11",
    ))

    # UC-14 additional: sepsis + HF + penicillin allergy combined
    scenarios.append(_make_scenario(
        usecaseid=_id("UC14", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-14: Sepsis + HF + penicillin allergy — combined safety deviations",
        testtype="Positive", priority="P0",
        pathway_id="nice-ng51-sepsis",
        patient_context=_simple_patient(
            "UC14-COMBO", 68, "male",
            conditions=[{"code": "pneumonia"}, {"code": "heart_failure"}],
            allergies=[{"substance": "penicillin", "category": "medication", "reaction": "anaphylaxis", "severity": "severe"}],
            vital_signs={"heart_rate": 115, "systolic_bp": 85, "temperature": 39.2},
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["safety_override", "contraindication_flagged"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Cautious fluids + alternative antimicrobial in deviation register",
        compliance_tags="NICE,GDPR",
        notes="Triple combination: sepsis + HF + penicillin allergy",
        use_case_ref="UC-14",
        expected_requires_signoff=True,
    ))

    # UC-17 additional: deviation register for moderate complexity patient
    scenarios.append(_make_scenario(
        usecaseid=_id("UC17", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-17: Moderate complexity — deviation register with mixed severities",
        testtype="Positive", priority="P1",
        pathway_id="nice-ng28-diabetes-type2",
        patient_context=_simple_patient(
            "UC17-MOD", 68, "female",
            conditions=[
                {"code": "type_2_diabetes"},
                {"code": "ckd_stage_4"},
                {"code": "diabetic_foot_ulcer"},
            ],
            medications=[{"code": "metformin"}],
            observations=[
                {"code": "egfr", "value": 25, "unit": "mL/min/1.73m2"},
                {"code": "hba1c", "value": 80, "unit": "mmol/mol"},
            ],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=[
            "contraindication_flagged", "activity_added", "urgency_elevated", "intensity_increased",
        ],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Deviation register with major and moderate entries",
        compliance_tags="NICE,GDPR",
        notes="Moderate complexity with foot ulcer + CKD + high HbA1c",
        use_case_ref="UC-17",
        expected_requires_signoff=True,
    ))

    # UC-15/16: Governance and audit — standard pathway with audit check
    for i, pathway in enumerate([
        "nice-ng106-heart-failure",
        "nice-ng28-diabetes-type2",
        "nice-ng115-copd",
    ]):
        scenarios.append(_make_scenario(
            usecaseid=_id("UC16", "Positive"),
            component="PathwayPersonaliser",
            scenario=f"UC-16: Audit trail verification — {pathway.split('-')[-1]}",
            testtype="Positive", priority="P1",
            pathway_id=pathway,
            patient_context=_simple_patient(
                f"UC16-{i}", 55, "male",
                conditions=[{"code": "heart_failure" if "heart" in pathway else "type_2_diabetes" if "diabetes" in pathway else "copd"}],
            ),
            expected_status="personalised_pathway_returned",
            expected_modifications=[], expected_safety_alerts=[],
            pre_conditions="Pathway loaded",
            post_conditions="Audit entry created with pseudonymised patient ID",
            compliance_tags="NICE,GDPR,Caldicott",
            notes="Verifies audit trail is created for every personalisation",
            use_case_ref="UC-16",
        ))

    # Fill remaining positive scenarios to reach 85
    # UC-02: additional HF+CKD variant
    scenarios.append(_make_scenario(
        usecaseid=_id("UC02", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-02: HF + CKD3 (eGFR=42) — renal-safe approach no MRA block",
        testtype="Positive", priority="P1",
        pathway_id="nice-ng106-heart-failure",
        patient_context=_simple_patient(
            "UC02-HF-EXT", 71, "female",
            conditions=[{"code": "heart_failure"}, {"code": "ckd_stage_3"}],
            observations=[{"code": "egfr", "value": 42, "unit": "mL/min/1.73m2"}],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["sequence_changed", "urgency_elevated"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Renal-safe but MRA still allowed at eGFR 42",
        compliance_tags="NICE,GDPR",
        notes="CKD3 triggers renal-safe but not MRA contraindication",
        use_case_ref="UC-02",
    ))

    # UC-03: lactate exactly at boundary
    scenarios.append(_make_scenario(
        usecaseid=_id("UC03", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-03: Lactate 4.2 — above critical threshold safety guardrail",
        testtype="Positive", priority="P0",
        pathway_id="nice-ng51-sepsis",
        patient_context=_simple_patient(
            "UC03-LAC", 58, "male",
            conditions=[{"code": "pneumonia"}],
            observations=[{"code": "lactate", "value": 4.2, "unit": "mmol/L"}],
            vital_signs={"heart_rate": 120, "systolic_bp": 78},
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["urgency_elevated"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Lactate critical safety deviation documented",
        compliance_tags="NICE,GDPR",
        notes="Lactate 4.2 > 4.0 triggers critical escalation",
        use_case_ref="UC-03",
    ))

    # UC-06: HF + CKD + MRA contraindication (eGFR < 30)
    scenarios.append(_make_scenario(
        usecaseid=_id("UC06", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-06: HF + CKD eGFR=24 — MRA contraindicated",
        testtype="Positive", priority="P0",
        pathway_id="nice-ng106-heart-failure",
        patient_context=_simple_patient(
            "UC06-MRA", 74, "male",
            conditions=[{"code": "heart_failure"}, {"code": "ckd_stage_4"}],
            observations=[{"code": "egfr", "value": 24, "unit": "mL/min/1.73m2"}],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["contraindication_flagged"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="MRA contraindication at eGFR < 30",
        compliance_tags="NICE,GDPR,BNF",
        notes="MRA contraindicated at eGFR < 30",
        use_case_ref="UC-06",
        expected_requires_signoff=True,
    ))

    # UC-08: HF polypharmacy 8 meds
    scenarios.append(_make_scenario(
        usecaseid=_id("UC08", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-08: HF polypharmacy 8 meds — review prioritised",
        testtype="Positive", priority="P1",
        pathway_id="nice-ng106-heart-failure",
        patient_context=_simple_patient(
            "UC08-HF8", 66, "male",
            conditions=[{"code": "heart_failure"}],
            medications=[{"code": f"hfmed{j}"} for j in range(8)],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["sequence_changed"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="HF polypharmacy review prioritised",
        compliance_tags="NICE,GDPR",
        notes="8 meds triggers HF-specific polypharmacy review (threshold 5)",
        use_case_ref="UC-08",
    ))

    # UC-12: HIV + sepsis
    scenarios.append(_make_scenario(
        usecaseid=_id("UC12", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-12: Sepsis + HIV — immunocompromised broader cover variant 4",
        testtype="Positive", priority="P0",
        pathway_id="nice-ng51-sepsis",
        patient_context=_simple_patient(
            "UC12-HIV", 45, "female",
            conditions=[{"code": "cellulitis"}, {"code": "hiv", "display": "HIV"}],
            vital_signs={"heart_rate": 100, "temperature": 38.4},
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["intensity_increased", "urgency_elevated"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Broader cover and lower threshold documented",
        compliance_tags="NICE,GDPR",
        notes="HIV triggers immunocompromised rule",
        use_case_ref="UC-12",
    ))

    # UC-18: COPD frequent exacerbator — 3 admissions
    scenarios.append(_make_scenario(
        usecaseid=_id("UC18", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-18: COPD frequent exacerbator — 3 admissions in 12mo",
        testtype="Positive", priority="P1",
        pathway_id="nice-ng115-copd",
        patient_context=_simple_patient(
            "UC18-3ADM", 70, "female",
            conditions=[{"code": "copd"}],
            encounters=[
                {"encounter_id": "E1", "encounter_type": "inpatient", "date": "2026-03-01T00:00:00", "reason": "COPD"},
                {"encounter_id": "E2", "encounter_type": "inpatient", "date": "2025-12-01T00:00:00", "reason": "COPD"},
                {"encounter_id": "E3", "encounter_type": "emergency", "date": "2025-08-01T00:00:00", "reason": "COPD"},
            ],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["intensity_increased", "activity_added"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Self-management plan + enhanced management",
        compliance_tags="NICE,GDPR",
        notes="3 admissions triggers enhanced management",
        use_case_ref="UC-18",
    ))

    # UC-15: Governance currency check scenario (tests pathway loads with governance)
    scenarios.append(_make_scenario(
        usecaseid=_id("UC15", "Positive"),
        component="PathwayPersonaliser",
        scenario="UC-15: Pathway with governance metadata — currency verification",
        testtype="Positive", priority="P1",
        pathway_id="who-maternal-anc",
        patient_context=_simple_patient(
            "UC15-GOV", 30, "female",
            conditions=[{"code": "pregnancy"}],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=[], expected_safety_alerts=[],
        pre_conditions="Pathway loaded with governance metadata including superseded source",
        post_conditions="Pathway returned — governance metadata accessible for audit",
        compliance_tags="WHO,NICE,GDPR",
        notes="Verifies pathway with superseded source (CG62→NG201) still loads correctly",
        use_case_ref="UC-15",
    ))

    # ════════════════════════════════════════════════════════════════
    # NEGATIVE SCENARIOS (10)
    # ════════════════════════════════════════════════════════════════

    # NEG-1: No pathway match
    scenarios.append(_make_scenario(
        usecaseid=_id("UCNEG", "Negative"),
        component="PathwayPersonaliser",
        scenario="NEG: Non-existent pathway ID",
        testtype="Negative", priority="P1",
        pathway_id="nice-ng999-nonexistent",
        patient_context=_simple_patient("NEG-001", 50, "male"),
        expected_status="pathway_not_found",
        expected_modifications=[], expected_safety_alerts=[],
        pre_conditions="Pathway does not exist in repository",
        post_conditions="Appropriate error returned, no deviation register",
        compliance_tags="GDPR",
        notes="Tests graceful handling of missing pathway",
        use_case_ref="UC-01",
    ))

    # NEG-2: No conditions, no mods needed but frailty below threshold
    scenarios.append(_make_scenario(
        usecaseid=_id("UCNEG", "Negative"),
        component="PathwayPersonaliser",
        scenario="NEG: Frailty 'mild' — below threshold, no adaptation expected",
        testtype="Negative", priority="P1",
        pathway_id="nice-ng106-heart-failure",
        patient_context=_simple_patient("NEG-002", 55, "male", frailty_score="mild"),
        expected_status="personalised_pathway_returned",
        expected_modifications=[], expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="No deviations — mild frailty does not trigger adaptation",
        compliance_tags="NICE,GDPR",
        notes="Mild frailty should NOT trigger frailty rule",
        use_case_ref="UC-07",
        expected_deviation_count=0,
    ))

    # NEG-3: eGFR normal — no renal modification
    scenarios.append(_make_scenario(
        usecaseid=_id("UCNEG", "Negative"),
        component="PathwayPersonaliser",
        scenario="NEG: Normal eGFR=75 — no renal modification expected",
        testtype="Negative", priority="P1",
        pathway_id="nice-ng28-diabetes-type2",
        patient_context=_simple_patient(
            "NEG-003", 55, "male",
            conditions=[{"code": "type_2_diabetes"}],
            medications=[{"code": "metformin"}],
            observations=[{"code": "egfr", "value": 75, "unit": "mL/min/1.73m2"}],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=[], expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="No metformin contraindication — eGFR is normal",
        compliance_tags="NICE,GDPR",
        notes="eGFR 75 should NOT trigger renal modification",
        use_case_ref="UC-06",
        expected_deviation_count=0,
    ))

    # NEG-4: No penicillin allergy — no antimicrobial change
    scenarios.append(_make_scenario(
        usecaseid=_id("UCNEG", "Negative"),
        component="PathwayPersonaliser",
        scenario="NEG: No penicillin allergy — standard antimicrobial for sepsis",
        testtype="Negative", priority="P1",
        pathway_id="nice-ng51-sepsis",
        patient_context=_simple_patient(
            "NEG-004", 60, "male",
            conditions=[{"code": "pneumonia"}],
            vital_signs={"heart_rate": 100, "temperature": 38.5},
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=[], expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Standard antimicrobial — no allergy modification",
        compliance_tags="NICE,GDPR",
        notes="No penicillin allergy means no antimicrobial deviation",
        use_case_ref="UC-13",
        expected_deviation_count=0,
    ))

    # NEG-5: Maternal age 35 — below AMA threshold
    scenarios.append(_make_scenario(
        usecaseid=_id("UCNEG", "Negative"),
        component="PathwayPersonaliser",
        scenario="NEG: Maternal age 35 — below AMA threshold, standard monitoring",
        testtype="Negative", priority="P1",
        pathway_id="who-maternal-anc",
        patient_context=_simple_patient(
            "NEG-005", 35, "female",
            conditions=[{"code": "pregnancy"}],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=[], expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Standard ANC — no advanced maternal age adaptation",
        compliance_tags="WHO,NICE,GDPR",
        notes="Age 35 is below the 40+ AMA threshold",
        use_case_ref="UC-10",
        expected_deviation_count=0,
    ))

    # NEG-6: Only 3 medications — below polypharmacy threshold
    scenarios.append(_make_scenario(
        usecaseid=_id("UCNEG", "Negative"),
        component="PathwayPersonaliser",
        scenario="NEG: Only 3 medications — no polypharmacy review",
        testtype="Negative", priority="P1",
        pathway_id="nice-ng28-diabetes-type2",
        patient_context=_simple_patient(
            "NEG-006", 55, "male",
            conditions=[{"code": "type_2_diabetes"}],
            medications=[{"code": "metformin"}, {"code": "gliclazide"}, {"code": "atorvastatin"}],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=[], expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="No polypharmacy review — below threshold",
        compliance_tags="NICE,GDPR",
        notes="3 meds is below both 5-med HF and 10-med general thresholds",
        use_case_ref="UC-08",
        expected_deviation_count=0,
    ))

    # NEG-7: No HF with sepsis — no cautious fluids
    scenarios.append(_make_scenario(
        usecaseid=_id("UCNEG", "Negative"),
        component="PathwayPersonaliser",
        scenario="NEG: Sepsis without HF — standard fluid resuscitation",
        testtype="Negative", priority="P1",
        pathway_id="nice-ng51-sepsis",
        patient_context=_simple_patient(
            "NEG-007", 45, "male",
            conditions=[{"code": "pneumonia"}],
            vital_signs={"heart_rate": 105, "systolic_bp": 90, "temperature": 39.0},
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=[], expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Standard fluid resuscitation — no HF comorbidity",
        compliance_tags="NICE,GDPR",
        notes="No HF means no cautious fluid override",
        use_case_ref="UC-14",
        expected_deviation_count=0,
    ))

    # NEG-8: No language barrier — no interpreter
    scenarios.append(_make_scenario(
        usecaseid=_id("UCNEG", "Negative"),
        component="PathwayPersonaliser",
        scenario="NEG: No language barrier — no interpreter service",
        testtype="Negative", priority="P1",
        pathway_id="nice-ng106-heart-failure",
        patient_context=_simple_patient(
            "NEG-008", 60, "male",
            conditions=[{"code": "heart_failure"}],
            social_history={"language_barrier": False, "interpreter_needed": False},
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=[], expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="No interpreter service added",
        compliance_tags="NICE,GDPR",
        notes="No language barrier means no interpreter deviation",
        use_case_ref="UC-09",
        expected_deviation_count=0,
    ))

    # NEG-9: COPD with only 1 admission — below frequent exacerbator threshold
    scenarios.append(_make_scenario(
        usecaseid=_id("UCNEG", "Negative"),
        component="PathwayPersonaliser",
        scenario="NEG: COPD with 1 admission — below frequent exacerbator threshold",
        testtype="Negative", priority="P1",
        pathway_id="nice-ng115-copd",
        patient_context=_simple_patient(
            "NEG-009", 62, "male",
            conditions=[{"code": "copd"}],
            encounters=[
                {"encounter_id": "E1", "encounter_type": "inpatient", "date": "2026-01-10T00:00:00", "reason": "COPD exacerbation"},
            ],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=[], expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Standard COPD management — 1 admission is below threshold",
        compliance_tags="NICE,GDPR",
        notes="1 admission does not trigger frequent exacerbator",
        use_case_ref="UC-18",
        expected_deviation_count=0,
    ))

    # NEG-10: Normal potassium — no safety alert
    scenarios.append(_make_scenario(
        usecaseid=_id("UCNEG", "Negative"),
        component="PathwayPersonaliser",
        scenario="NEG: Normal potassium K+=4.2 — no safety guardrail",
        testtype="Negative", priority="P1",
        pathway_id="nice-ng106-heart-failure",
        patient_context=_simple_patient(
            "NEG-010", 65, "male",
            conditions=[{"code": "heart_failure"}],
            observations=[{"code": "potassium", "value": 4.2, "unit": "mmol/L"}],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=[], expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="No safety override — potassium is normal",
        compliance_tags="NICE,GDPR",
        notes="K+ 4.2 is within normal range",
        use_case_ref="UC-03",
        expected_deviation_count=0,
    ))

    # ════════════════════════════════════════════════════════════════
    # EDGE CASES (5)
    # ════════════════════════════════════════════════════════════════

    # EDGE-1: eGFR exactly at boundary (30)
    scenarios.append(_make_scenario(
        usecaseid=_id("UCEDGE", "Edge"),
        component="PathwayPersonaliser",
        scenario="EDGE: eGFR exactly 30 — boundary for metformin contraindication",
        testtype="Edge", priority="P0",
        pathway_id="nice-ng28-diabetes-type2",
        patient_context=_simple_patient(
            "EDGE-001", 60, "male",
            conditions=[{"code": "type_2_diabetes"}],
            medications=[{"code": "metformin"}],
            observations=[{"code": "egfr", "value": 30, "unit": "mL/min/1.73m2"}],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=[], expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="eGFR=30 is AT boundary — metformin NOT contraindicated (rule is < 30)",
        compliance_tags="NICE,GDPR",
        notes="Boundary test: eGFR=30 should NOT trigger contraindication (rule uses < 30)",
        use_case_ref="UC-06",
        expected_deviation_count=0,
    ))

    # EDGE-2: Potassium exactly 6.0 — at boundary
    scenarios.append(_make_scenario(
        usecaseid=_id("UCEDGE", "Edge"),
        component="PathwayPersonaliser",
        scenario="EDGE: Potassium exactly 6.0 — at critical boundary",
        testtype="Edge", priority="P0",
        pathway_id="nice-ng106-heart-failure",
        patient_context=_simple_patient(
            "EDGE-002", 70, "male",
            conditions=[{"code": "heart_failure"}],
            observations=[{"code": "potassium", "value": 6.0, "unit": "mmol/L"}],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=[], expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="K+=6.0 is AT boundary — safety check uses > 6.0",
        compliance_tags="NICE,GDPR",
        notes="Boundary: K+=6.0 should NOT trigger (rule uses > 6.0)",
        use_case_ref="UC-03",
        expected_deviation_count=0,
    ))

    # EDGE-3: Maternal age exactly 40 — at AMA threshold
    scenarios.append(_make_scenario(
        usecaseid=_id("UCEDGE", "Edge"),
        component="PathwayPersonaliser",
        scenario="EDGE: Maternal age exactly 40 — AMA threshold boundary",
        testtype="Edge", priority="P0",
        pathway_id="who-maternal-anc",
        patient_context=_simple_patient(
            "EDGE-003", 40, "female",
            conditions=[{"code": "pregnancy"}],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["intensity_increased"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Age 40 IS at threshold — rule uses >= 40, so should trigger",
        compliance_tags="WHO,NICE,GDPR",
        notes="Boundary: age=40 should trigger (rule uses >= 40)",
        use_case_ref="UC-10",
    ))

    # EDGE-4: Maximum complexity — all rules fire simultaneously
    scenarios.append(_make_scenario(
        usecaseid=_id("UCEDGE", "Edge"),
        component="PathwayPersonaliser",
        scenario="EDGE: Maximum complexity — polypharmacy + frailty + CKD + recurrent admissions + transport barrier",
        testtype="Edge", priority="P0",
        pathway_id="nice-ng106-heart-failure",
        patient_context=_simple_patient(
            "EDGE-004", 82, "male",
            conditions=[
                {"code": "heart_failure"}, {"code": "ckd_stage_4"},
                {"code": "type_2_diabetes"}, {"code": "copd"},
            ],
            medications=[{"code": f"med{j}", "display": f"Med {j}"} for j in range(15)],
            observations=[
                {"code": "egfr", "value": 20, "unit": "mL/min/1.73m2"},
                {"code": "potassium", "value": 5.8, "unit": "mmol/L"},
            ],
            frailty_score="severe",
            social_history={"transport_access": "none", "language_barrier": True, "interpreter_needed": True},
            encounters=[
                {"encounter_id": f"E{j}", "encounter_type": "inpatient", "date": f"202{6 if j<2 else 5}-{j+1:02d}-15T00:00:00", "reason": "HF"}
                for j in range(4)
            ],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=[
            "sequence_changed", "urgency_elevated", "contraindication_flagged",
            "follow_up_adapted", "intensity_reduced", "intensity_increased",
            "activity_added",
        ],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Large deviation register with multiple severity levels",
        compliance_tags="NICE,GDPR,Caldicott",
        notes="Maximum complexity stress test — all cross-pathway and HF rules fire",
        use_case_ref="UC-17",
        expected_requires_signoff=True,
    ))

    # EDGE-5: Exactly 10 medications — at polypharmacy boundary
    scenarios.append(_make_scenario(
        usecaseid=_id("UCEDGE", "Edge"),
        component="PathwayPersonaliser",
        scenario="EDGE: Exactly 10 medications — at polypharmacy threshold boundary",
        testtype="Edge", priority="P0",
        pathway_id="nice-ng28-diabetes-type2",
        patient_context=_simple_patient(
            "EDGE-005", 65, "male",
            conditions=[{"code": "type_2_diabetes"}],
            medications=[{"code": f"med{j}", "display": f"Med {j}"} for j in range(10)],
        ),
        expected_status="personalised_pathway_returned",
        expected_modifications=["sequence_changed"],
        expected_safety_alerts=[],
        pre_conditions="Pathway loaded",
        post_conditions="Exactly 10 meds IS at threshold — rule uses >= 10, so should trigger",
        compliance_tags="NICE,GDPR",
        notes="Boundary: 10 meds should trigger (rule uses >= 10)",
        use_case_ref="UC-08",
    ))

    return scenarios


if __name__ == "__main__":
    scenarios = generate()

    # Verify counts
    positive = sum(1 for s in scenarios if s["testtype"] == "Positive")
    negative = sum(1 for s in scenarios if s["testtype"] == "Negative")
    edge = sum(1 for s in scenarios if s["testtype"] == "Edge")
    total = len(scenarios)

    print(f"Generated {total} scenarios: {positive} positive, {negative} negative, {edge} edge")
    print(f"Ratios: {positive/total*100:.0f}% / {negative/total*100:.0f}% / {edge/total*100:.0f}%")

    # Verify use case coverage
    use_cases_covered = set()
    for s in scenarios:
        ref = s.get("use_case_ref", "")
        if ref:
            use_cases_covered.add(ref)
    print(f"Use cases covered: {sorted(use_cases_covered)}")

    # Write to file
    output = SCENARIOS_DIR / "scenarios_use_cases.json"
    output.write_text(json.dumps(scenarios, indent=2), encoding="utf-8")
    print(f"Written to {output}")
