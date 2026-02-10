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

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(f"{url}/rpc", json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            return result
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return {"error": str(e)}

async def simulate_patient_visit():
    """Simulate a complete patient visit through HelixCare."""
    patient_id = f"PAT-{int(time.time())}"
    visit_id = f"VISIT-{int(time.time())}"

    print("🏥 Starting Patient Visit Simulation")
    print(f"   Patient ID: {patient_id}")
    print(f"   Visit ID: {visit_id}")
    print("=" * 50)

    # Step 1: Triage
    print("\\n1. TRIAGE - Initial assessment")
    triage_result = await make_jsonrpc_call(
        BASE_URLS["triage"],
        "tasks/sendSubscribe",
        {
            "patient_id": patient_id,
            "visit_id": visit_id,
            "symptoms": "Severe chest pain, shortness of breath, nausea",
            "vital_signs": {"blood_pressure": "160/95", "heart_rate": 110, "temperature": 98.6, "oxygen_saturation": 95, "respiratory_rate": 22},
            "chief_complaint": "Chest pain for 2 hours",
            "arrival_time": datetime.now().isoformat()
        },
        f"{visit_id}-triage"
    )
    await asyncio.sleep(2)

    # Step 2: Diagnosis
    print("\\n2. DIAGNOSIS - Medical assessment")
    diagnosis_result = await make_jsonrpc_call(
        BASE_URLS["diagnosis"],
        "tasks/sendSubscribe",
        {
            "patient_id": patient_id,
            "visit_id": visit_id,
            "symptoms": "Severe chest pain, shortness of breath, nausea",
            "vital_signs": {"blood_pressure": "160/95", "heart_rate": 110, "temperature": 98.6, "oxygen_saturation": 95, "respiratory_rate": 22},
            "differential_diagnosis": ["Acute Coronary Syndrome", "Pulmonary Embolism", "Pneumothorax"]
        },
        f"{visit_id}-diagnosis"
    )
    await asyncio.sleep(3)

    # Step 3: Imaging
    print("\\n3. IMAGING - Diagnostic imaging")
    imaging_result = await make_jsonrpc_call(
        BASE_URLS["imaging"],
        "tasks/sendSubscribe",
        {
            "patient_id": patient_id,
            "visit_id": visit_id,
            "orders": [
                {"type": "chest_xray", "priority": "urgent", "indication": "Rule out pneumothorax, pulmonary edema"},
                {"type": "ecg", "priority": "urgent", "indication": "Evaluate for ST changes, arrhythmias"}
            ]
        },
        f"{visit_id}-imaging"
    )
    await asyncio.sleep(4)

    # Step 4: Pharmacy
    print("\\n4. PHARMACY - Medication recommendations")
    pharmacy_result = await make_jsonrpc_call(
        BASE_URLS["pharmacy"],
        "tasks/sendSubscribe",
        {
            "patient_id": patient_id,
            "visit_id": visit_id,
            "medication_orders": [
                {"drug": "Aspirin", "dose": "325mg", "route": "oral", "frequency": "once", "indication": "Antiplatelet therapy"},
                {"drug": "Nitroglycerin", "dose": "0.4mg", "route": "sublingual", "frequency": "as needed", "indication": "Chest pain relief"}
            ],
            "allergies": ["Penicillin"],
            "renal_function": "Normal"
        },
        f"{visit_id}-pharmacy"
    )
    await asyncio.sleep(2)

    # Step 5: Bed Manager
    print("\\n5. BED MANAGER - Admission coordination")
    bed_result = await make_jsonrpc_call(
        BASE_URLS["bed_manager"],
        "tasks/sendSubscribe",
        {
            "patient_id": patient_id,
            "visit_id": visit_id,
            "admission_type": "emergency",
            "required_monitoring": "telemetry",
            "estimated_los": "2-3 days",
            "special_requirements": ["Cardiac monitoring", "Frequent vital signs"]
        },
        f"{visit_id}-bed"
    )
    await asyncio.sleep(2)

    # Step 6: Care Coordinator
    print("\\n6. CARE COORDINATOR - Journey orchestration")
    coordinator_result = await make_jsonrpc_call(
        BASE_URLS["coordinator"],
        "tasks/sendSubscribe",
        {
            "patient_id": patient_id,
            "visit_id": visit_id,
            "journey_type": "cardiac_chest_pain",
            "current_phase": "diagnostic_workup",
            "coordination_tasks": ["Monitor cardiac enzymes", "Consult cardiology", "Schedule stress test"],
            "risk_level": "high"
        },
        f"{visit_id}-coordinator"
    )
    await asyncio.sleep(3)

    # Step 7: Discharge
    print("\\n7. DISCHARGE - Planning and summary")
    discharge_result = await make_jsonrpc_call(
        BASE_URLS["discharge"],
        "tasks/sendSubscribe",
        {
            "patient_id": patient_id,
            "visit_id": visit_id,
            "discharge_diagnosis": "Unstable Angina",
            "discharge_disposition": "home",
            "followup_instructions": ["Follow up with cardiology in 1 week", "Continue aspirin 325mg daily"]
        },
        f"{visit_id}-discharge"
    )
    await asyncio.sleep(2)

    # Step 8: Follow-up
    print("\\n8. FOLLOW-UP - Post-discharge care")
    followup_result = await make_jsonrpc_call(
        BASE_URLS["followup"],
        "tasks/sendSubscribe",
        {
            "patient_id": patient_id,
            "visit_id": visit_id,
            "followup_schedule": [
                {"type": "cardiology_clinic", "when": (datetime.now() + timedelta(days=7)).isoformat(), "purpose": "Follow-up after unstable angina"},
                {"type": "stress_test", "when": (datetime.now() + timedelta(days=14)).isoformat(), "purpose": "Risk stratification"}
            ]
        },
        f"{visit_id}-followup"
    )
    await asyncio.sleep(2)

    print("\\n✅ Patient visit simulation completed!")
    print(f"   Total duration: ~25 seconds")
    print(f"   Agents exercised: {len(BASE_URLS)}")
    print("=" * 50)

async def main():
    """Main execution function."""
    print("🚀 HelixCare Patient Visit Simulator")
    print("This will simulate a complete patient journey through all agents")
    print("Make sure all agents are running before proceeding")
    print()

    try:
        await simulate_patient_visit()
    except KeyboardInterrupt:
        print("\\n⏹️  Simulation interrupted")
    except Exception as e:
        print(f"\\n❌ Simulation failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())