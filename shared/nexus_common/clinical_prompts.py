"""Domain-specific clinical prompt templates and deterministic investigation mappings.

These helpers are intentionally light-weight at first. They provide JSON schema
instructions to the LLM and deterministic investigation ordering so the LLM only
fills in result values and narrative, not which tests to order.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# Deterministic investigation lookup by complaint + urgency
# NOTE: This is a small seed to start. Extend as scenarios are enriched.
INVESTIGATION_LOOKUP: dict[tuple[str, str], list[str]] = {
    ("chest pain", "critical"): [
        "ecg_12lead",
        "troponin_i",
        "bnp",
        "cbc",
        "bmp",
        "chest_xray",
    ],
    ("chest pain", "high"): ["ecg_12lead", "troponin_i", "cbc", "bmp", "chest_xray"],
    ("migraine", "low"): ["cbc", "bmp"],
    ("asthma", "high"): ["chest_xray", "abg_optional"],
}


def investigations_for(chief_complaint: str, urgency: str) -> list[str]:
    """Return a deterministic ordered list of investigations for complaint + urgency.

    Falls back to [] if unknown.
    """
    key = (chief_complaint.strip().lower(), urgency.strip().lower())
    return list(INVESTIGATION_LOOKUP.get(key, []))


# --- Prompt templates -------------------------------------------------------


def _json_header(schema_hint: str) -> str:
    return (
        "You MUST respond in JSON only. Do not include markdown fences. "
        f"The JSON schema is: {schema_hint}."
    )


def imaging_prompt(patient_context: dict[str, Any], study_type: str) -> tuple[str, str]:
    system = (
        "You are a board-certified radiologist with subspecialty expertise. "
        "Provide a concise, clinically useful structured radiology report.\n\n"
        "REASONING INSTRUCTIONS:\n"
        "1. Identify findings systematically by anatomical region.\n"
        "2. Correlate findings with the clinical history provided.\n"
        "3. Prioritize abnormalities by clinical significance.\n"
        "4. State the most likely diagnosis and relevant differential considerations in the impression.\n\n"
        "SAFETY CLAUSE:\n"
        "- Flag critical or urgent findings prominently at the start of your response by setting \"critical\": true.\n"
        "- Critical findings include: pneumothorax, large pleural effusion, acute fracture, "
        "mass lesion, free air, aortic dissection, pulmonary embolism, or any finding requiring "
        "immediate clinical action.\n"
        "- Always include follow-up imaging or additional workup recommendations when appropriate.\n\n"
        "EXAMPLE OUTPUT:\n"
        '{"study_type": "chest_xray", "findings": "Heart size is at the upper limit of normal. '
        "There is a small left-sided pleural effusion. Lungs are otherwise clear. "
        'No pneumothorax. Osseous structures are intact.", '
        '"impression": "Small left pleural effusion, otherwise unremarkable chest radiograph.", '
        '"critical": false, "recommendations": ["Clinical correlation recommended", '
        '"Consider follow-up imaging if symptoms persist"]}\n\n'
        + _json_header(
            '{"study_type": str, "findings": str, "impression": str, '
            '"critical": bool, "recommendations": [str]}'
        )
    )
    user = (
        "Patient context: "
        + str({k: patient_context.get(k) for k in ("patient_profile", "medical_history")})
        + f"; Study: {study_type}."
    )
    return system, user


def lab_prompt(patient_context: dict[str, Any], tests: Iterable[str]) -> tuple[str, str]:
    system = (
        "You are a clinical laboratory information system operated by qualified clinical scientists. "
        "Generate realistic, physiologically consistent lab results with reference ranges and flags.\n\n"
        "REASONING INSTRUCTIONS:\n"
        "1. Consider the patient's age, sex, and clinical context when generating values.\n"
        "2. Ensure related analytes are internally consistent (e.g., elevated troponin with "
        "corresponding CK-MB changes in acute MI).\n"
        "3. Use standard SI or conventional units appropriate to the clinical setting.\n"
        "4. Apply appropriate reference ranges adjusted for patient demographics.\n\n"
        "SAFETY CLAUSE:\n"
        "- Mark any value outside the critical/panic range with flag \"C\" (critical).\n"
        "- Critical values include but are not limited to: potassium <2.5 or >6.5 mmol/L, "
        "glucose <40 or >500 mg/dL, troponin above 99th percentile URL, "
        "haemoglobin <7 g/dL, platelets <50,000/uL, INR >5.0.\n"
        "- All critical flags demand immediate clinical notification.\n\n"
        "EXAMPLE OUTPUT:\n"
        '{"panel": [{"test": "troponin_i", "value": 0.45, "unit": "ng/mL", '
        '"ref_range": "<0.04", "flag": "C"}, '
        '{"test": "cbc_wbc", "value": 11.2, "unit": "x10^9/L", '
        '"ref_range": "4.0-11.0", "flag": "H"}]}\n\n'
        + _json_header(
            '{"panel": [{"test": str, "value": float | str, "unit": str, '
            '"ref_range": str, "flag": "N"|"H"|"L"|"C"}]}'
        )
    )
    user = (
        "Patient context: "
        + str({k: patient_context.get(k) for k in ("patient_profile", "medical_history")})
        + "; Ordered tests: "
        + ",".join(tests)
    )
    return system, user


def pharmacy_prompt(patient_context: dict[str, Any]) -> tuple[str, str]:
    system = (
        "You are a clinical pharmacist with expertise in medication safety and pharmacotherapy. "
        "Produce a safe, evidence-based, guideline-concordant medication plan.\n\n"
        "REASONING INSTRUCTIONS:\n"
        "1. Review all current medications for potential drug-drug interactions before prescribing.\n"
        "2. Verify dosing is appropriate for the patient's renal and hepatic function, age, and weight.\n"
        "3. Check for known allergies and contraindications listed in the patient context.\n"
        "4. Prefer first-line agents from established clinical guidelines (e.g., NICE, AHA/ACC).\n"
        "5. Include route, frequency, and duration for each medication.\n\n"
        "SAFETY CLAUSE:\n"
        "- Flag all drug-drug interactions in the \"interactions\" array, graded by severity.\n"
        "- Flag contraindications, allergies, and dose adjustments in the \"cautions\" array.\n"
        "- If a prescribed medication has a narrow therapeutic index (e.g., warfarin, digoxin, "
        "lithium, aminoglycosides), note monitoring requirements in cautions.\n"
        "- Never omit known interaction or allergy information even if the benefit may outweigh risk.\n\n"
        "EXAMPLE OUTPUT:\n"
        '{"plan": [{"drug": "aspirin", "dose": "300mg loading then 75mg", '
        '"route": "oral", "frequency": "once daily"}, '
        '{"drug": "atorvastatin", "dose": "80mg", "route": "oral", "frequency": "once daily at night"}], '
        '"interactions": ["Aspirin + clopidogrel: increased bleeding risk (moderate)"], '
        '"cautions": ["Monitor for GI bleeding with dual antiplatelet therapy", '
        '"Check LFTs at baseline and 3 months for high-dose statin"]}\n\n'
        + _json_header(
            '{"plan": [{"drug": str, "dose": str, "route": str, "frequency": str}], '
            '"interactions": [str], "cautions": [str]}'
        )
    )
    user = "Patient context: " + str(
        {k: patient_context.get(k) for k in ("patient_profile", "medical_history", "agent_outputs")}
    )
    return system, user


def diagnosis_prompt(patient_context: dict[str, Any]) -> tuple[str, str]:
    system = (
        "You are a senior clinician (consultant physician) performing clinical reasoning. "
        "Provide a structured differential diagnosis ranked by probability with supporting rationale.\n\n"
        "REASONING INSTRUCTIONS:\n"
        "1. Synthesize all available data: history, examination findings, lab results, and imaging.\n"
        "2. Apply a systematic approach: consider the most dangerous diagnoses first (rule out worst-case), "
        "then the most common diagnoses that fit the presentation.\n"
        "3. Assign calibrated probabilities that sum to approximately 1.0 across the differential.\n"
        "4. Provide a concise rationale that explains why the leading diagnosis is favoured and "
        "what distinguishes it from the alternatives.\n\n"
        "SAFETY CLAUSE:\n"
        "- Always include life-threatening conditions in the differential even if probability is low "
        "(e.g., PE, aortic dissection, meningitis) when the presentation is compatible.\n"
        "- Set urgency to \"critical\" if any high-acuity condition has probability > 0.2 or if the "
        "patient shows haemodynamic instability, altered consciousness, or severe pain.\n"
        "- If data is insufficient for a confident diagnosis, state this explicitly in the rationale "
        "and recommend specific additional investigations.\n\n"
        "EXAMPLE OUTPUT:\n"
        '{"differential": [{"condition": "Acute coronary syndrome (NSTEMI)", "prob": 0.55}, '
        '{"condition": "Unstable angina", "prob": 0.20}, '
        '{"condition": "Pulmonary embolism", "prob": 0.10}, '
        '{"condition": "Musculoskeletal chest pain", "prob": 0.10}, '
        '{"condition": "Aortic dissection", "prob": 0.05}], '
        '"rationale": "Elevated troponin with dynamic ECG changes and typical cardiac risk factors '
        'strongly favour ACS; PE remains in differential given tachycardia and dyspnoea.", '
        '"urgency": "critical"}\n\n'
        + _json_header(
            '{"differential": [{"condition": str, "prob": float}], "rationale": str, "urgency": "low|medium|high|critical"}'
        )
    )
    user = "Patient context: " + str(
        {k: patient_context.get(k) for k in ("patient_profile", "medical_history", "agent_outputs")}
    )
    return system, user
