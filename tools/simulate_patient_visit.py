#!/usr/bin/env python3
"""
Realistic Patient Visit Scenario Runner for HelixCare AI Hospital

This script simulates a complete patient journey through the HelixCare system,
generating events that are visible in the Command Centre dashboard.
"""

import asyncio
import json
import time
import httpx
from datetime import datetime, timedelta
from typing import Dict, Any

# Add the project root to Python path to import shared modules
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.nexus_common.auth import mint_jwt

# Configuration
BASE_URLS = {
    "triage": "http://localhost:8021",
    "diagnosis": "http://localhost:8022",
    "imaging": "http://localhost:8024",
    "pharmacy": "http://localhost:8025",
    "bed_manager": "http://localhost:8026",
    "discharge": "http://localhost:8027",
    "followup": "http://localhost:8028",
    "coordinator": "http://localhost:8029"
}

def create_jwt_token(subject: str = "test-patient-visit") -> str:
    """Create JWT token for authentication."""
    return mint_jwt(subject, "dev-secret-change-me")

async def make_jsonrpc_call(url: str, method: str, params: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    """Make a JSON-RPC call to an agent."""
    headers = {
        "Authorization": f"Bearer {create_jwt_token()}",
        "Content-Type": "application/json"
    }

    payload = {
        "jsonrpc": "2.0",
        "id": task_id,
        "method": method,
        "params": params
    }

    print(f"📞 Calling {url}/rpc - Method: {method}")
    print(f"   Params: {json.dumps(params, indent=2)}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(f"{url}/rpc", json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            print(f"   ✅ Response: {json.dumps(result, indent=2)}")
            return result
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return {"error": str(e)}

async def simulate_patient_visit():
    """Simulate a complete patient visit through HelixCare."""

    # Generate unique patient and visit IDs
    patient_id = f"PAT-{int(time.time())}"
    visit_id = f"VISIT-{int(time.time())}"

    print("🏥 Starting HelixCare Patient Visit Simulation")
    print(f"   Patient ID: {patient_id}")
    print(f"   Visit ID: {visit_id}")
    print("=" * 60)

    # Step 1: ED Triage - Patient arrives with chest pain
    print("\n🚑 Step 1: ED Triage - Patient Arrival")
    triage_params = {
        "patient_id": patient_id,
        "visit_id": visit_id,
        "symptoms": "Severe chest pain, shortness of breath, nausea",
        "vital_signs": {
            "blood_pressure": "160/95",
            "heart_rate": 110,
            "temperature": 98.6,
            "oxygen_saturation": 95,
            "respiratory_rate": 22
        },
        "chief_complaint": "Chest pain for 2 hours",
        "arrival_time": datetime.now().isoformat()
    }

    triage_result = await make_jsonrpc_call(BASE_URLS["triage"], "tasks/sendSubscribe", triage_params, f"{visit_id}-triage")
    await asyncio.sleep(2)  # Allow events to propagate

    # Step 2: Diagnosis - AI analysis of symptoms and vitals
    print("\n🔍 Step 2: AI Diagnosis - Analyzing Symptoms")
    diagnosis_params = {
        "patient_id": patient_id,
        "visit_id": visit_id,
        "symptoms": triage_params["symptoms"],
        "vital_signs": triage_params["vital_signs"],
        "triage_assessment": "High priority - possible cardiac event",
        "differential_diagnosis": ["Acute Coronary Syndrome", "Pulmonary Embolism", "Pneumothorax"]
    }

    diagnosis_result = await make_jsonrpc_call(BASE_URLS["diagnosis"], "tasks/sendSubscribe", diagnosis_params, f"{visit_id}-diagnosis")
    await asyncio.sleep(3)  # Allow AI processing

    # Step 3: Imaging - Order chest X-ray and ECG
    print("\n🩻 Step 3: Imaging - Ordering Diagnostic Tests")
    imaging_params = {
        "patient_id": patient_id,
        "visit_id": visit_id,
        "orders": [
            {
                "type": "chest_xray",
                "priority": "urgent",
                "indication": "Rule out pneumothorax, pulmonary edema"
            },
            {
                "type": "ecg",
                "priority": "urgent",
                "indication": "Evaluate for ST changes, arrhythmias"
            }
        ],
        "clinical_context": "Chest pain with cardiac risk factors"
    }

    imaging_result = await make_jsonrpc_call(BASE_URLS["imaging"], "tasks/sendSubscribe", imaging_params, f"{visit_id}-imaging")
    await asyncio.sleep(4)  # Simulate imaging processing

    # Step 4: Pharmacy - Prepare cardiac medications
    print("\n💊 Step 4: Pharmacy - Preparing Medications")
    pharmacy_params = {
        "patient_id": patient_id,
        "visit_id": visit_id,
        "medication_orders": [
            {
                "drug": "Aspirin",
                "dose": "325mg",
                "route": "oral",
                "frequency": "once",
                "indication": "Antiplatelet therapy"
            },
            {
                "drug": "Nitroglycerin",
                "dose": "0.4mg",
                "route": "sublingual",
                "frequency": "as needed",
                "indication": "Chest pain relief"
            }
        ],
        "allergies": ["Penicillin"],
        "renal_function": "Normal"
    }

    pharmacy_result = await make_jsonrpc_call(BASE_URLS["pharmacy"], "tasks/sendSubscribe", pharmacy_params, f"{visit_id}-pharmacy")
    await asyncio.sleep(2)

    # Step 5: Bed Management - Assign telemetry bed
    print("\n🛏️ Step 5: Bed Management - Assigning Telemetry Bed")
    bed_params = {
        "patient_id": patient_id,
        "visit_id": visit_id,
        "admission_type": "emergency",
        "required_monitoring": "telemetry",
        "estimated_los": "2-3 days",
        "special_requirements": ["Cardiac monitoring", "Frequent vital signs"],
        "admission_diagnosis": "Chest pain - rule out MI"
    }

    bed_result = await make_jsonrpc_call(BASE_URLS["bed_manager"], "tasks/sendSubscribe", bed_params, f"{visit_id}-bed")
    await asyncio.sleep(2)

    # Step 6: Care Coordinator - Orchestrate full patient journey
    print("\n🎯 Step 6: Care Coordination - Full Journey Orchestration")
    coordinator_params = {
        "patient_id": patient_id,
        "visit_id": visit_id,
        "journey_type": "cardiac_chest_pain",
        "current_phase": "diagnostic_workup",
        "coordination_tasks": [
            "Monitor cardiac enzymes",
            "Consult cardiology",
            "Schedule stress test",
            "Patient education"
        ],
        "risk_level": "high",
        "estimated_completion": (datetime.now() + timedelta(hours=4)).isoformat()
    }

    coordinator_result = await make_jsonrpc_call(BASE_URLS["coordinator"], "tasks/sendSubscribe", coordinator_params, f"{visit_id}-coordinator")
    await asyncio.sleep(3)

    # Step 7: Discharge Planning - Patient stabilizes
    print("\n📋 Step 7: Discharge Planning - Patient Stabilizes")
    discharge_params = {
        "patient_id": patient_id,
        "visit_id": visit_id,
        "discharge_diagnosis": "Unstable Angina",
        "discharge_disposition": "home",
        "followup_instructions": [
            "Follow up with cardiology in 1 week",
            "Continue aspirin 325mg daily",
            "Return immediately if chest pain recurs"
        ],
        "medications_on_discharge": [
            "Aspirin 325mg daily",
            "Atorvastatin 40mg daily",
            "Metoprolol 25mg twice daily"
        ],
        "lifestyle_modifications": [
            "Low sodium diet",
            "Regular exercise program",
            "Smoking cessation"
        ]
    }

    discharge_result = await make_jsonrpc_call(BASE_URLS["discharge"], "tasks/sendSubscribe", discharge_params, f"{visit_id}-discharge")
    await asyncio.sleep(2)

    # Step 8: Follow-up Scheduling - Post-discharge care
    print("\n📅 Step 8: Follow-up Scheduling - Post-Discharge Care")
    followup_params = {
        "patient_id": patient_id,
        "visit_id": visit_id,
        "followup_schedule": [
            {
                "type": "cardiology_clinic",
                "when": (datetime.now() + timedelta(days=7)).isoformat(),
                "provider": "Dr. Smith",
                "purpose": "Follow-up after unstable angina"
            },
            {
                "type": "stress_test",
                "when": (datetime.now() + timedelta(days=14)).isoformat(),
                "facility": "Cardiac Imaging Center",
                "purpose": "Risk stratification"
            }
        ],
        "monitoring_plan": "Home blood pressure monitoring",
        "education_topics": ["Heart healthy diet", "Medication adherence"]
    }

    followup_result = await make_jsonrpc_call(BASE_URLS["followup"], "tasks/sendSubscribe", followup_params, f"{visit_id}-followup")
    await asyncio.sleep(2)

    print("\n" + "=" * 60)
    print("🏥 HelixCare Patient Visit Simulation Complete!")
    print(f"   Patient ID: {patient_id}")
    print(f"   Visit ID: {visit_id}")
    print("   Status: All systems activated and events generated")
    print("   Check Command Centre dashboard at http://localhost:8099")
    print("=" * 60)

async def main():
    """Main execution function."""
    try:
        await simulate_patient_visit()
    except KeyboardInterrupt:
        print("\n🛑 Simulation interrupted by user")
    except Exception as e:
        print(f"\n❌ Simulation failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())