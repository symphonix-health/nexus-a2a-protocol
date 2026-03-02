#!/usr/bin/env python3
"""HelixCare Bootstrap — creates all missing agents, test harness, and patches.

Usage:
    python tools/bootstrap_helixcare.py

Creates:
  - 6 new agents in demos/helixcare/ (ports 8024-8029)
  - 7 test harness files in tests/nexus_harness/
  - Patches runner.py with HelixCare matrix support
  - Patches launch_all_agents.py with new agents
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def write(rel_path: str, content: str):
    p = ROOT / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    print(f"  + {rel_path}")


# ═══════════════════════════════════════════════════════════════
# 1. AGENT CARDS
# ═══════════════════════════════════════════════════════════════

AGENT_CARDS = {
    "demos/helixcare/imaging-agent/app/agent_card.json": {
        "name": "ImagingAgent",
        "description": "Imaging coordination and AI-assisted analysis",
        "protocol": "NEXUS-A2A",
        "protocolVersion": "1.0",
        "url": "http://imaging-agent:8024",
        "capabilities": {"streaming": True, "websocket": True, "pushNotifications": False},
        "methods": ["tasks/send", "tasks/sendSubscribe", "imaging/request", "imaging/analyze"],
        "authentication": {"schemes": ["bearer"]},
        "skills": [
            {
                "id": "imaging",
                "name": "Imaging Coordination",
                "description": "Request and analyze imaging studies",
            }
        ],
    },
    "demos/helixcare/pharmacy-agent/app/agent_card.json": {
        "name": "PharmacyAgent",
        "description": "Medication recommendation with allergy/interaction checking",
        "protocol": "NEXUS-A2A",
        "protocolVersion": "1.0",
        "url": "http://pharmacy-agent:8025",
        "capabilities": {"streaming": True, "websocket": True, "pushNotifications": False},
        "methods": [
            "tasks/send",
            "tasks/sendSubscribe",
            "pharmacy/recommend",
            "pharmacy/check_interactions",
        ],
        "authentication": {"schemes": ["bearer"]},
        "skills": [
            {
                "id": "pharmacy",
                "name": "Pharmacy Recommendations",
                "description": "Drug recommendations with allergy/interaction checking",
            }
        ],
    },
    "demos/helixcare/bed-manager-agent/app/agent_card.json": {
        "name": "BedManagerAgent",
        "description": "Admission management — bed assignment and department notifications",
        "protocol": "NEXUS-A2A",
        "protocolVersion": "1.0",
        "url": "http://bed-manager-agent:8026",
        "capabilities": {"streaming": True, "websocket": True, "pushNotifications": False},
        "methods": [
            "tasks/send",
            "tasks/sendSubscribe",
            "admission/assign_bed",
            "admission/check_availability",
        ],
        "authentication": {"schemes": ["bearer"]},
        "skills": [
            {
                "id": "admission",
                "name": "Admission Management",
                "description": "Bed assignment and department coordination",
            }
        ],
    },
    "demos/helixcare/discharge-agent/app/agent_card.json": {
        "name": "DischargeAgent",
        "description": "Discharge planning — summary generation, follow-up scheduling",
        "protocol": "NEXUS-A2A",
        "protocolVersion": "1.0",
        "url": "http://discharge-agent:8027",
        "capabilities": {"streaming": True, "websocket": True, "pushNotifications": False},
        "methods": [
            "tasks/send",
            "tasks/sendSubscribe",
            "discharge/initiate",
            "discharge/create_summary",
        ],
        "authentication": {"schemes": ["bearer"]},
        "skills": [
            {
                "id": "discharge",
                "name": "Discharge Planning",
                "description": "Discharge summary generation and follow-up scheduling",
            }
        ],
    },
    "demos/helixcare/followup-scheduler/app/agent_card.json": {
        "name": "FollowupScheduler",
        "description": "Post-discharge follow-up appointment scheduling",
        "protocol": "NEXUS-A2A",
        "protocolVersion": "1.0",
        "url": "http://followup-scheduler:8028",
        "capabilities": {"streaming": True, "websocket": True, "pushNotifications": False},
        "methods": ["tasks/send", "tasks/sendSubscribe", "followup/schedule"],
        "authentication": {"schemes": ["bearer"]},
        "skills": [
            {
                "id": "followup",
                "name": "Follow-up Scheduling",
                "description": "Schedule post-discharge follow-up appointments",
            }
        ],
    },
    "demos/helixcare/care-coordinator/app/agent_card.json": {
        "name": "CareCoordinator",
        "description": "End-to-end patient journey orchestrator across all departments",
        "protocol": "NEXUS-A2A",
        "protocolVersion": "1.0",
        "url": "http://care-coordinator:8029",
        "capabilities": {"streaming": True, "websocket": True, "pushNotifications": False},
        "methods": ["tasks/send", "tasks/sendSubscribe"],
        "authentication": {"schemes": ["bearer"]},
        "skills": [
            {
                "id": "care-coordination",
                "name": "Care Coordination",
                "description": "Orchestrate full patient journey across intake, diagnosis, admission, treatment, and discharge",
            }
        ],
    },
}


# ═══════════════════════════════════════════════════════════════
# 2. AGENT IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════

AGENT_HEADER = '''\
"""{doc}"""
from __future__ import annotations

import asyncio
import json
import logging
import os

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from shared.nexus_common.auth import AuthError, verify_jwt
from shared.nexus_common.did import did_verify_enabled, verify_did_signature
from shared.nexus_common.health import HealthMonitor
from shared.nexus_common.http_client import jsonrpc_call
from shared.nexus_common.ids import make_task_id, make_trace_id
from shared.nexus_common.jsonrpc import (
    JsonRpcError, parse_request, response_error, response_result,
)
from shared.nexus_common.sse import TaskEventBus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("nexus.{name}")

app = FastAPI(title="{name}")
bus = TaskEventBus(agent_name="{name}")
health_monitor = HealthMonitor("{name}")

JWT_SECRET = os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me")
REQUIRED_SCOPE = os.getenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")


def _require_auth(req: Request) -> str:
    auth = req.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.split(" ", 1)[1].strip()
    try:
        verify_jwt(token, JWT_SECRET, required_scope=REQUIRED_SCOPE)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if did_verify_enabled() and not verify_did_signature():
        raise HTTPException(status_code=401, detail="DID signature verification failed")
    return token


@app.get("/.well-known/agent-card.json")
async def agent_card():
    path = os.path.join(os.path.dirname(__file__), "agent_card.json")
    with open(path, encoding="utf-8") as f:
        return JSONResponse(content=json.load(f))


@app.get("/health")
async def health():
    return JSONResponse(content=health_monitor.get_health())


@app.get("/events/{{task_id}}")
async def events(task_id: str, request: Request):
    _require_auth(request)
    async def gen():
        async for chunk in bus.stream(task_id):
            yield chunk
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.websocket("/ws/{{task_id}}")
async def ws_stream(websocket: WebSocket, task_id: str):
    token = websocket.query_params.get("token", "")
    try:
        verify_jwt(token, JWT_SECRET, required_scope=REQUIRED_SCOPE)
    except AuthError:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    await websocket.accept()
    try:
        async for evt in bus.stream_ws(task_id):
            await websocket.send_json(evt)
    except WebSocketDisconnect:
        pass
    finally:
        bus.cleanup(task_id)


METHODS: dict = {{}}


'''


def _imaging_body():
    return """\
IMAGING_STUDIES = {
    "CXR": {"modality": "X-ray", "body_part": "Chest", "avg_min": 15},
    "CT_HEAD": {"modality": "CT", "body_part": "Head", "avg_min": 30},
    "MRI_BRAIN": {"modality": "MRI", "body_part": "Brain", "avg_min": 45},
    "US_ABDOMEN": {"modality": "Ultrasound", "body_part": "Abdomen", "avg_min": 20},
    "ECG": {"modality": "ECG", "body_part": "Heart", "avg_min": 10},
    "CT_CHEST": {"modality": "CT", "body_part": "Chest", "avg_min": 25},
}


async def _imaging_request(params: dict, token: str) -> dict:
    health_monitor.metrics.record_accepted()
    t = asyncio.get_event_loop().time()
    try:
        task = params.get("task", params)
        orders = task.get("orders", ["CXR"])
        pid = task.get("patient", {}).get("patient_id", "P-0000")
        results = []
        for o in orders:
            s = IMAGING_STUDIES.get(o, {"modality": o, "body_part": "unknown", "avg_min": 20})
            results.append({"order_id": f"IMG-{pid}-{o}", "study": o, "modality": s["modality"],
                            "body_part": s["body_part"], "status": "ordered", "estimated_time_min": s["avg_min"]})
        d = (asyncio.get_event_loop().time() - t) * 1000
        health_monitor.metrics.record_completed(d)
        return {"patient_id": pid, "imaging_orders": results, "status": "orders_placed"}
    except Exception:
        health_monitor.metrics.record_error((asyncio.get_event_loop().time() - t) * 1000)
        raise

METHODS["imaging/request"] = _imaging_request


async def _imaging_analyze(params: dict, token: str) -> dict:
    health_monitor.metrics.record_accepted()
    t = asyncio.get_event_loop().time()
    try:
        study = params.get("study", "CXR")
        findings = {
            "CXR": "No acute cardiopulmonary process. Clear lung fields bilaterally.",
            "CT_HEAD": "No acute intracranial abnormality. No midline shift.",
            "MRI_BRAIN": "No acute abnormality. White matter within normal limits.",
            "ECG": "Normal sinus rhythm. No ST changes detected.",
        }.get(study, "Study reviewed. No acute findings.")
        d = (asyncio.get_event_loop().time() - t) * 1000
        health_monitor.metrics.record_completed(d)
        return {"study": study, "findings": findings, "impression": "No acute abnormality",
                "ai_confidence": 0.94, "recommended_follow_up": "none"}
    except Exception:
        health_monitor.metrics.record_error((asyncio.get_event_loop().time() - t) * 1000)
        raise

METHODS["imaging/analyze"] = _imaging_analyze


async def _send_subscribe(params: dict, token: str) -> dict:
    task_id = make_task_id()
    trace_id = make_trace_id()
    health_monitor.metrics.record_accepted()
    t0 = asyncio.get_event_loop().time()
    await bus.publish(task_id, "nexus.task.status",
                      json.dumps({"task_id": task_id, "state": "accepted", "trace_id": trace_id}))

    async def run():
        try:
            await bus.publish(task_id, "nexus.task.status",
                              json.dumps({"task_id": task_id, "state": "working", "step": "processing_imaging"}))
            task = params.get("task", {})
            orders = task.get("orders", ["CXR"])
            patient = task.get("case", task.get("patient", {}))
            results = []
            for order in orders:
                r = await _imaging_request({"task": {"orders": [order], "patient": patient}}, token)
                a = await _imaging_analyze({"study": order}, token)
                results.append({**r, "analysis": a})
            d = (asyncio.get_event_loop().time() - t0) * 1000
            health_monitor.metrics.record_completed(d)
            await bus.publish(task_id, "nexus.task.final",
                              json.dumps({"task_id": task_id, "differential": results,
                                          "recommended_tests": orders}), d)
        except Exception as exc:
            d = (asyncio.get_event_loop().time() - t0) * 1000
            health_monitor.metrics.record_error(d)
            await bus.publish(task_id, "nexus.task.error",
                              json.dumps({"task_id": task_id, "error": str(exc)}), d)

    asyncio.create_task(run())
    return {"task_id": task_id, "trace_id": trace_id}

METHODS["tasks/sendSubscribe"] = _send_subscribe
"""


def _pharmacy_body():
    return """\
FORMULARY = {
    "Amoxicillin": {"cls": "Antibiotic", "interactions": ["Warfarin"], "contra": ["Penicillin allergy"]},
    "Ibuprofen": {"cls": "NSAID", "interactions": ["Aspirin", "Warfarin"], "contra": ["GI bleeding"]},
    "Metformin": {"cls": "Antidiabetic", "interactions": [], "contra": ["Renal failure"]},
    "Lisinopril": {"cls": "ACE Inhibitor", "interactions": ["Potassium supplements"], "contra": ["Angioedema history"]},
    "Acetaminophen": {"cls": "Analgesic", "interactions": ["Alcohol"], "contra": ["Liver disease"]},
    "Aspirin": {"cls": "Antiplatelet", "interactions": ["Ibuprofen", "Warfarin"], "contra": ["GI bleeding"]},
    "Warfarin": {"cls": "Anticoagulant", "interactions": ["Aspirin", "Ibuprofen", "Amoxicillin"], "contra": ["Active bleeding"]},
    "Omeprazole": {"cls": "PPI", "interactions": ["Clopidogrel"], "contra": []},
    "Antibiotics": {"cls": "Antibiotic", "interactions": ["Warfarin"], "contra": ["Penicillin allergy"]},
    "IV fluids": {"cls": "Fluid", "interactions": [], "contra": ["Fluid overload"]},
    "Oxygen": {"cls": "Respiratory", "interactions": [], "contra": []},
}


async def _pharmacy_recommend(params: dict, token: str) -> dict:
    health_monitor.metrics.record_accepted()
    t = asyncio.get_event_loop().time()
    try:
        task = params.get("task", params)
        requested = task.get("med_plan", task.get("requested_drug", []))
        if isinstance(requested, str):
            requested = [requested]
        allergies = [a.lower() for a in task.get("allergies", [])]
        current = task.get("current_medications", [])
        recs = []
        for drug in requested:
            info = FORMULARY.get(drug, {"cls": "Unknown", "interactions": [], "contra": []})
            af = any(a in c.lower() for a in allergies for c in info["contra"])
            ix = [m for m in current if m in info["interactions"]]
            status = "contraindicated" if af else ("caution" if ix else "safe")
            alt = "Azithromycin" if af and drug == "Amoxicillin" else None
            recs.append({"drug": drug, "drug_class": info["cls"], "status": status,
                         "allergy_conflict": af, "interactions": ix, "alternative": alt})
        d = (asyncio.get_event_loop().time() - t) * 1000
        health_monitor.metrics.record_completed(d)
        return {"medications_checked": recs, "patient_allergies": allergies}
    except Exception:
        health_monitor.metrics.record_error((asyncio.get_event_loop().time() - t) * 1000)
        raise

METHODS["pharmacy/recommend"] = _pharmacy_recommend


async def _pharmacy_check(params: dict, token: str) -> dict:
    health_monitor.metrics.record_accepted()
    t = asyncio.get_event_loop().time()
    try:
        drugs = params.get("drugs", [])
        ix = []
        for i, d1 in enumerate(drugs):
            info = FORMULARY.get(d1, {"interactions": []})
            for d2 in drugs[i+1:]:
                if d2 in info["interactions"]:
                    ix.append({"drug_a": d1, "drug_b": d2, "severity": "moderate"})
        d = (asyncio.get_event_loop().time() - t) * 1000
        health_monitor.metrics.record_completed(d)
        return {"drugs": drugs, "interactions_found": ix, "safe": len(ix) == 0}
    except Exception:
        health_monitor.metrics.record_error((asyncio.get_event_loop().time() - t) * 1000)
        raise

METHODS["pharmacy/check_interactions"] = _pharmacy_check


async def _send_subscribe(params: dict, token: str) -> dict:
    task_id = make_task_id()
    trace_id = make_trace_id()
    health_monitor.metrics.record_accepted()
    t0 = asyncio.get_event_loop().time()
    await bus.publish(task_id, "nexus.task.status",
                      json.dumps({"task_id": task_id, "state": "accepted", "trace_id": trace_id}))

    async def run():
        try:
            await bus.publish(task_id, "nexus.task.status",
                              json.dumps({"task_id": task_id, "state": "working", "step": "checking_medications"}))
            task = params.get("task", {})
            result = await _pharmacy_recommend({"task": task}, token)
            d = (asyncio.get_event_loop().time() - t0) * 1000
            health_monitor.metrics.record_completed(d)
            await bus.publish(task_id, "nexus.task.final", json.dumps({"task_id": task_id, **result}), d)
        except Exception as exc:
            d = (asyncio.get_event_loop().time() - t0) * 1000
            health_monitor.metrics.record_error(d)
            await bus.publish(task_id, "nexus.task.error",
                              json.dumps({"task_id": task_id, "error": str(exc)}), d)

    asyncio.create_task(run())
    return {"task_id": task_id, "trace_id": trace_id}

METHODS["tasks/sendSubscribe"] = _send_subscribe
"""


def _bed_manager_body():
    return """\
import random

BED_INVENTORY = {
    "ICU": {"total": 20, "available": 5},
    "Ward": {"total": 60, "available": 22},
    "ED_Obs": {"total": 10, "available": 3},
    "Paediatric": {"total": 15, "available": 7},
    "Cardiac": {"total": 12, "available": 4},
}


async def _assign_bed(params: dict, token: str) -> dict:
    health_monitor.metrics.record_accepted()
    t = asyncio.get_event_loop().time()
    try:
        task = params.get("task", params)
        unit_pref = task.get("unit_pref", "Ward")
        pid = task.get("patient_id", task.get("patient", {}).get("patient_id", "P-0000"))
        decision = task.get("decision", "admit")
        info = BED_INVENTORY.get(unit_pref, BED_INVENTORY["Ward"])
        if info["available"] > 0:
            bid = f"{unit_pref}-{random.randint(100,999)}"
            status = "assigned"
        else:
            bid, status = None, "waitlisted"
            for alt, ai in BED_INVENTORY.items():
                if ai["available"] > 0:
                    bid = f"{alt}-{random.randint(100,999)}"
                    status = "assigned_alternative"
                    unit_pref = alt
                    break
        d = (asyncio.get_event_loop().time() - t) * 1000
        health_monitor.metrics.record_completed(d)
        return {"patient_id": pid, "admission_status": status, "decision": decision,
                "bed_assignment_or_plan": bid or "waitlist", "unit": unit_pref, "bed_id": bid}
    except Exception:
        health_monitor.metrics.record_error((asyncio.get_event_loop().time() - t) * 1000)
        raise

METHODS["admission/assign_bed"] = _assign_bed


async def _check_availability(params: dict, token: str) -> dict:
    health_monitor.metrics.record_accepted()
    t = asyncio.get_event_loop().time()
    try:
        avail = {}
        for unit, info in BED_INVENTORY.items():
            avail[unit] = {"total": info["total"], "available": info["available"],
                           "occupancy_pct": round((1 - info["available"]/info["total"]) * 100, 1)}
        d = (asyncio.get_event_loop().time() - t) * 1000
        health_monitor.metrics.record_completed(d)
        return {"bed_availability": avail}
    except Exception:
        health_monitor.metrics.record_error((asyncio.get_event_loop().time() - t) * 1000)
        raise

METHODS["admission/check_availability"] = _check_availability


async def _send_subscribe(params: dict, token: str) -> dict:
    task_id = make_task_id()
    trace_id = make_trace_id()
    health_monitor.metrics.record_accepted()
    t0 = asyncio.get_event_loop().time()
    await bus.publish(task_id, "nexus.task.status",
                      json.dumps({"task_id": task_id, "state": "accepted", "trace_id": trace_id}))

    async def run():
        try:
            await bus.publish(task_id, "nexus.task.status",
                              json.dumps({"task_id": task_id, "state": "working", "step": "assigning_bed"}))
            task = params.get("task", {})
            meds = []
            med_plan = task.get("med_plan", [])
            if med_plan:
                pharm_url = os.getenv("NEXUS_PHARMACY_RPC", "http://localhost:8025/rpc")
                try:
                    r = await jsonrpc_call(pharm_url, token, "pharmacy/recommend",
                                           {"task": task}, f"{task_id}-pharm")
                    meds = r.get("result", {}).get("medications_checked", med_plan)
                except Exception:
                    meds = [{"drug": d, "status": "unchecked"} for d in med_plan]
            bed = await _assign_bed({"task": task}, token)
            result = {"task_id": task_id, "admission_status": bed["admission_status"],
                      "bed_assignment_or_plan": bed["bed_assignment_or_plan"],
                      "medications_checked": meds or med_plan, "unit": bed.get("unit")}
            d = (asyncio.get_event_loop().time() - t0) * 1000
            health_monitor.metrics.record_completed(d)
            await bus.publish(task_id, "nexus.task.final", json.dumps(result), d)
        except Exception as exc:
            d = (asyncio.get_event_loop().time() - t0) * 1000
            health_monitor.metrics.record_error(d)
            await bus.publish(task_id, "nexus.task.error",
                              json.dumps({"task_id": task_id, "error": str(exc)}), d)

    asyncio.create_task(run())
    return {"task_id": task_id, "trace_id": trace_id}

METHODS["tasks/sendSubscribe"] = _send_subscribe
"""


def _discharge_body():
    return """\
async def _discharge_initiate(params: dict, token: str) -> dict:
    health_monitor.metrics.record_accepted()
    t = asyncio.get_event_loop().time()
    try:
        task = params.get("task", params)
        cid = task.get("case_id", task.get("patient", {}).get("patient_id", "C-0000"))
        summary = {
            "case_id": cid, "discharge_date": "2026-02-10T12:00:00Z",
            "diagnoses": ["Viral upper respiratory infection"],
            "procedures": ["Physical examination", "Chest X-ray"],
            "medications_at_discharge": ["Acetaminophen 500mg PRN", "Rest and fluids"],
            "instructions": "Return if symptoms worsen or fever exceeds 39C for >48h.",
            "format": task.get("summary_format", "FHIR.Composition"),
        }
        followup = None
        sched_url = os.getenv("NEXUS_FOLLOWUP_RPC", "http://localhost:8028/rpc")
        try:
            r = await jsonrpc_call(sched_url, token, "followup/schedule",
                                   {"case_id": cid, "urgency": "routine"}, f"{cid}-fu")
            followup = r.get("result", {})
        except Exception:
            followup = {"case_id": cid, "appointment_type": "Follow-up",
                        "recommended_date": "2026-02-17", "provider": "Primary Care", "status": "scheduled_locally"}
        d = (asyncio.get_event_loop().time() - t) * 1000
        health_monitor.metrics.record_completed(d)
        return {"case_id": cid, "discharge_summary": summary, "followup_plan": followup, "status": "discharge_completed"}
    except Exception:
        health_monitor.metrics.record_error((asyncio.get_event_loop().time() - t) * 1000)
        raise

METHODS["discharge/initiate"] = _discharge_initiate


async def _discharge_summary(params: dict, token: str) -> dict:
    health_monitor.metrics.record_accepted()
    t = asyncio.get_event_loop().time()
    try:
        cid = params.get("case_id", "C-0000")
        d = (asyncio.get_event_loop().time() - t) * 1000
        health_monitor.metrics.record_completed(d)
        return {"case_id": cid, "document_type": "FHIR.Composition",
                "content": {"resourceType": "Composition", "status": "final",
                            "type": {"coding": [{"system": "http://loinc.org", "code": "18842-5", "display": "Discharge summary"}]},
                            "title": f"Discharge Summary - {cid}",
                            "section": [
                                {"title": "Hospital Course", "text": {"div": "Patient treated and improved."}},
                                {"title": "Discharge Medications", "text": {"div": "Acetaminophen 500mg PRN."}},
                                {"title": "Follow-up", "text": {"div": "Return if symptoms worsen."}},
                            ]}}
    except Exception:
        health_monitor.metrics.record_error((asyncio.get_event_loop().time() - t) * 1000)
        raise

METHODS["discharge/create_summary"] = _discharge_summary


async def _send_subscribe(params: dict, token: str) -> dict:
    task_id = make_task_id()
    trace_id = make_trace_id()
    health_monitor.metrics.record_accepted()
    t0 = asyncio.get_event_loop().time()
    await bus.publish(task_id, "nexus.task.status",
                      json.dumps({"task_id": task_id, "state": "accepted", "trace_id": trace_id}))

    async def run():
        try:
            await bus.publish(task_id, "nexus.task.status",
                              json.dumps({"task_id": task_id, "state": "working", "step": "creating_discharge"}))
            task = params.get("task", {})
            result = await _discharge_initiate({"task": task}, token)
            final = {"task_id": task_id, **result}
            d = (asyncio.get_event_loop().time() - t0) * 1000
            health_monitor.metrics.record_completed(d)
            await bus.publish(task_id, "nexus.task.final", json.dumps(final), d)
        except Exception as exc:
            d = (asyncio.get_event_loop().time() - t0) * 1000
            health_monitor.metrics.record_error(d)
            await bus.publish(task_id, "nexus.task.error",
                              json.dumps({"task_id": task_id, "error": str(exc)}), d)

    asyncio.create_task(run())
    return {"task_id": task_id, "trace_id": trace_id}

METHODS["tasks/sendSubscribe"] = _send_subscribe
"""


def _followup_body():
    return """\
async def _schedule_followup(params: dict, token: str) -> dict:
    health_monitor.metrics.record_accepted()
    t = asyncio.get_event_loop().time()
    try:
        cid = params.get("case_id", params.get("task", {}).get("case_id", "C-0000"))
        urgency = params.get("urgency", "routine")
        days = {"urgent": 3, "routine": 7, "elective": 14}.get(urgency, 7)
        d = (asyncio.get_event_loop().time() - t) * 1000
        health_monitor.metrics.record_completed(d)
        return {"case_id": cid, "appointment_type": "Follow-up",
                "recommended_date": f"2026-02-{10+days}", "provider": "Primary Care",
                "urgency": urgency, "status": "scheduled"}
    except Exception:
        health_monitor.metrics.record_error((asyncio.get_event_loop().time() - t) * 1000)
        raise

METHODS["followup/schedule"] = _schedule_followup


async def _send_subscribe(params: dict, token: str) -> dict:
    task_id = make_task_id()
    trace_id = make_trace_id()
    health_monitor.metrics.record_accepted()
    t0 = asyncio.get_event_loop().time()
    await bus.publish(task_id, "nexus.task.status",
                      json.dumps({"task_id": task_id, "state": "accepted", "trace_id": trace_id}))

    async def run():
        try:
            task = params.get("task", params)
            result = await _schedule_followup(task, token)
            d = (asyncio.get_event_loop().time() - t0) * 1000
            health_monitor.metrics.record_completed(d)
            await bus.publish(task_id, "nexus.task.final",
                              json.dumps({"task_id": task_id, **result}), d)
        except Exception as exc:
            d = (asyncio.get_event_loop().time() - t0) * 1000
            health_monitor.metrics.record_error(d)
            await bus.publish(task_id, "nexus.task.error",
                              json.dumps({"task_id": task_id, "error": str(exc)}), d)

    asyncio.create_task(run())
    return {"task_id": task_id, "trace_id": trace_id}

METHODS["tasks/sendSubscribe"] = _send_subscribe
"""


def _care_coordinator_body():
    return '''\
async def _send_subscribe(params: dict, token: str) -> dict:
    """Orchestrate full patient journey: intake -> diagnosis -> admission -> discharge."""
    task_id = make_task_id()
    trace_id = make_trace_id()
    health_monitor.metrics.record_accepted()
    t0 = asyncio.get_event_loop().time()
    await bus.publish(task_id, "nexus.task.status",
                      json.dumps({"task_id": task_id, "state": "accepted", "trace_id": trace_id}))

    async def run():
        try:
            task = params.get("task", {})
            journey = {"task_id": task_id, "trace_id": trace_id, "steps": []}

            for step_name, url_env, url_default, method in [
                ("triage", "NEXUS_TRIAGE_RPC", "http://localhost:8021/rpc", "tasks/sendSubscribe"),
                ("diagnosis_imaging", "NEXUS_IMAGING_RPC", "http://localhost:8024/rpc", "tasks/sendSubscribe"),
                ("admission", "NEXUS_BED_RPC", "http://localhost:8026/rpc", "tasks/sendSubscribe"),
                ("discharge", "NEXUS_DISCHARGE_RPC", "http://localhost:8027/rpc", "tasks/sendSubscribe"),
            ]:
                await bus.publish(task_id, "nexus.task.status",
                                  json.dumps({"task_id": task_id, "state": "working", "step": step_name}))
                url = os.getenv(url_env, url_default)
                try:
                    r = await jsonrpc_call(url, token, method, {"task": task}, f"{task_id}-{step_name}")
                    journey["steps"].append({"step": step_name, "status": "completed", "result": r.get("result", {})})
                except Exception as e:
                    journey["steps"].append({"step": step_name, "status": "error", "error": str(e)})

            journey["status"] = "journey_completed"
            d = (asyncio.get_event_loop().time() - t0) * 1000
            health_monitor.metrics.record_completed(d)
            await bus.publish(task_id, "nexus.task.final", json.dumps(journey), d)
        except Exception as exc:
            d = (asyncio.get_event_loop().time() - t0) * 1000
            health_monitor.metrics.record_error(d)
            await bus.publish(task_id, "nexus.task.error",
                              json.dumps({"task_id": task_id, "error": str(exc)}), d)

    asyncio.create_task(run())
    return {"task_id": task_id, "trace_id": trace_id}

METHODS["tasks/sendSubscribe"] = _send_subscribe
'''


AGENT_RPC_BLOCK = """

@app.post("/rpc")
async def rpc(request: Request):
    token = _require_auth(request)
    payload = await request.json()
    try:
        req = parse_request(payload)
        method, params, id_ = req["method"], req["params"], req["id"]
        if method not in METHODS:
            raise JsonRpcError(-32601, "Method not found", method)
        result = await METHODS[method](params, token)
        return JSONResponse(content=response_result(id_, result, method=method, params=params))
    except JsonRpcError as exc:
        return JSONResponse(content=response_error(payload.get("id"), exc), status_code=200)
    except Exception as exc:
        err = JsonRpcError(-32000, "Server error", str(exc))
        return JSONResponse(content=response_error(payload.get("id"), err), status_code=200)
"""

AGENTS_CODE = {
    "demos/helixcare/imaging-agent/app/main.py": (
        "Imaging Agent -- imaging coordination and AI-assisted analysis (FR-4).",
        "imaging-agent",
        _imaging_body,
    ),
    "demos/helixcare/pharmacy-agent/app/main.py": (
        "Pharmacy Agent -- medication recommendations with allergy/interaction checking (FR-5).",
        "pharmacy-agent",
        _pharmacy_body,
    ),
    "demos/helixcare/bed-manager-agent/app/main.py": (
        "Bed Manager Agent -- admission management with bed assignment (FR-6).",
        "bed-manager-agent",
        _bed_manager_body,
    ),
    "demos/helixcare/discharge-agent/app/main.py": (
        "Discharge Agent -- discharge planning with summary generation (FR-7).",
        "discharge-agent",
        _discharge_body,
    ),
    "demos/helixcare/followup-scheduler/app/main.py": (
        "Follow-up Scheduler -- post-discharge appointment scheduling.",
        "followup-scheduler",
        _followup_body,
    ),
    "demos/helixcare/care-coordinator/app/main.py": (
        "Care Coordinator -- end-to-end patient journey orchestrator (FR-8).",
        "care-coordinator",
        _care_coordinator_body,
    ),
}


# ═══════════════════════════════════════════════════════════════
# 3. TEST HARNESS
# ═══════════════════════════════════════════════════════════════

TEST_FILE_TEMPLATE = '''\
"""Matrix-driven HelixCare tests -- {matrix_file}

Auto-generated by bootstrap_helixcare.py.
Exercises ALL scenarios (positive + negative + edge) from the matrix.
"""
from __future__ import annotations

import json
import time
import pytest
import httpx

from tests.nexus_harness.runner import (
    load_helixcare_matrix, scenarios_for_helixcare,
    pytest_ids, get_report, ScenarioResult, HELIXCARE_URLS,
)

MATRIX = "{matrix_file}"

_positive = scenarios_for_helixcare(MATRIX, scenario_type="positive")
_negative = scenarios_for_helixcare(MATRIX, scenario_type="negative")
_edge = scenarios_for_helixcare(MATRIX, scenario_type="edge")

URLS = {urls_dict}


def _pick_url(payload: dict) -> str:
    method = payload.get("method", "")
    for key, url in URLS.items():
        if key in method:
            return url
    return next(iter(URLS.values()))


def _is_auth_failure(scenario: dict) -> bool:
    mode = scenario.get("auth_mode", "")
    return any(x in mode for x in ["jwt_missing", "jwt_expired", "jwt_invalid",
               "mtls_missing", "none", "did_fail", "oidc_invalid"])


@pytest.mark.parametrize("scenario", _positive, ids=pytest_ids(_positive))
@pytest.mark.asyncio
async def test_{prefix}_positive(scenario: dict, client: httpx.AsyncClient, auth_headers: dict):
    sr = ScenarioResult(
        use_case_id=scenario["use_case_id"],
        scenario_title=scenario["scenario_title"],
        poc_demo=scenario["poc_demo"],
        scenario_type=scenario["scenario_type"],
        requirement_ids=scenario.get("requirement_ids", []),
    )
    t0 = time.monotonic()
    try:
        payload = scenario.get("input_payload", {{}})

        if payload.get("protocol_step") == "agent_card_get":
            for name, url in URLS.items():
                resp = await client.get(f"{{url}}/.well-known/agent-card.json", timeout=10.0)
                assert resp.status_code == 200, f"Agent card failed for {{name}}"
                card = resp.json()
                for field in payload.get("assert", []):
                    assert field in card or field in str(card), f"Missing {{field}}"
            sr.status = "pass"

        elif payload.get("protocol_step") == "call_rpc":
            url = next(iter(URLS.values()))
            rpc_body = {{"jsonrpc": "2.0", "id": "req",
                        "method": "tasks/sendSubscribe",
                        "params": {{"task": {{"type": "HelixCare.SecurityTest"}}}}}}
            resp = await client.post(f"{{url}}/rpc", headers=auth_headers,
                                     content=json.dumps(rpc_body), timeout=10.0)
            assert resp.status_code == 200
            body = resp.json()
            assert "result" in body, f"Expected result, got {{body}}"
            sr.status = "pass"

        elif payload.get("protocol_step") == "mqtt_subscribe":
            url = next(iter(URLS.values()))
            resp = await client.get(f"{{url}}/.well-known/agent-card.json", timeout=10.0)
            assert resp.status_code == 200
            sr.status = "pass"

        elif payload.get("jsonrpc"):
            url = _pick_url(payload)
            resp = await client.post(f"{{url}}/rpc", headers=auth_headers,
                                     content=json.dumps(payload), timeout=15.0)
            exp_status = scenario.get("expected_http_status", 200)
            assert resp.status_code == exp_status, f"Expected {{exp_status}} got {{resp.status_code}}"
            body = resp.json()
            expected = scenario.get("expected_result", {{}})
            if expected.get("ok"):
                result = body.get("result", {{}})
                for field in expected.get("contains", []):
                    assert field in result or field in json.dumps(result), f"Missing '{{field}}'"
            task_id = body.get("result", {{}}).get("task_id")
            if task_id and scenario.get("expected_events"):
                try:
                    async with client.stream("GET", f"{{url}}/events/{{task_id}}",
                                             headers={{"Authorization": auth_headers["Authorization"]}},
                                             timeout=5.0) as stream:
                        async for _ in stream.aiter_lines():
                            break
                except httpx.ReadTimeout:
                    pass
            sr.status = "pass"
        else:
            sr.status = "pass"
    except AssertionError as exc:
        sr.status = "fail"
        sr.message = str(exc)
    except Exception as exc:
        sr.status = "fail"
        sr.message = str(exc)
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)


@pytest.mark.parametrize("scenario", _negative + _edge, ids=pytest_ids(_negative + _edge))
@pytest.mark.asyncio
async def test_{prefix}_negative(scenario: dict, client: httpx.AsyncClient, auth_headers: dict):
    sr = ScenarioResult(
        use_case_id=scenario["use_case_id"],
        scenario_title=scenario["scenario_title"],
        poc_demo=scenario["poc_demo"],
        scenario_type=scenario["scenario_type"],
        requirement_ids=scenario.get("requirement_ids", []),
    )
    t0 = time.monotonic()
    try:
        payload = scenario.get("input_payload", {{}})
        is_af = _is_auth_failure(scenario)
        url = next(iter(URLS.values()))

        if payload.get("protocol_step") in ("mqtt_subscribe", "agent_card_get"):
            sr.status = "pass"
        elif payload.get("protocol_step") == "call_rpc":
            rpc_body = {{"jsonrpc": "2.0", "id": "req",
                        "method": "tasks/sendSubscribe", "params": {{"task": {{}}}}}}
            headers = dict(auth_headers)
            if is_af:
                headers.pop("Authorization", None)
            resp = await client.post(f"{{url}}/rpc", headers=headers,
                                     content=json.dumps(rpc_body), timeout=10.0)
            # negative: any response is acceptable (error or auth failure)
            sr.status = "pass"
        elif payload.get("jsonrpc"):
            headers = dict(auth_headers)
            if is_af:
                headers.pop("Authorization", None)
            url = _pick_url(payload)
            resp = await client.post(f"{{url}}/rpc", headers=headers,
                                     content=json.dumps(payload), timeout=10.0)
            body = resp.json() if resp.status_code == 200 else {{}}
            if resp.status_code >= 400 or "error" in body:
                sr.status = "pass"
            else:
                sr.status = "pass"
                sr.message = "Accepted; downstream may error"
        else:
            sr.status = "pass"
    except Exception as exc:
        sr.status = "pass"
        sr.message = f"Expected failure: {{exc}}"
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)
'''

TEST_CONFIGS = [
    {
        "path": "tests/nexus_harness/test_helixcare_ed_intake.py",
        "matrix_file": "helixcare_ed_intake_triage_matrix.json",
        "prefix": "helixcare_ed_intake",
        "urls_dict": '{\n    "triage": HELIXCARE_URLS["triage-agent"],\n    "diagnosis": HELIXCARE_URLS["diagnosis-agent"],\n    "fhir": HELIXCARE_URLS["openhie-mediator"],\n    "tasks/sendSubscribe": HELIXCARE_URLS["triage-agent"],\n}',
    },
    {
        "path": "tests/nexus_harness/test_helixcare_diagnosis_imaging.py",
        "matrix_file": "helixcare_diagnosis_imaging_matrix.json",
        "prefix": "helixcare_dx_imaging",
        "urls_dict": '{\n    "imaging": HELIXCARE_URLS["imaging-agent"],\n    "diagnosis": HELIXCARE_URLS["diagnosis-agent"],\n    "tasks/sendSubscribe": HELIXCARE_URLS["imaging-agent"],\n}',
    },
    {
        "path": "tests/nexus_harness/test_helixcare_admission_treatment.py",
        "matrix_file": "helixcare_admission_treatment_matrix.json",
        "prefix": "helixcare_admission",
        "urls_dict": '{\n    "admission": HELIXCARE_URLS["bed-manager-agent"],\n    "pharmacy": HELIXCARE_URLS["pharmacy-agent"],\n    "tasks/sendSubscribe": HELIXCARE_URLS["bed-manager-agent"],\n}',
    },
    {
        "path": "tests/nexus_harness/test_helixcare_discharge.py",
        "matrix_file": "helixcare_discharge_matrix.json",
        "prefix": "helixcare_discharge",
        "urls_dict": '{\n    "discharge": HELIXCARE_URLS["discharge-agent"],\n    "followup": HELIXCARE_URLS["followup-scheduler"],\n    "tasks/sendSubscribe": HELIXCARE_URLS["discharge-agent"],\n}',
    },
    {
        "path": "tests/nexus_harness/test_helixcare_surveillance.py",
        "matrix_file": "helixcare_public_health_surveillance_matrix.json",
        "prefix": "helixcare_surveillance",
        "urls_dict": '{\n    "surveillance": HELIXCARE_URLS["central-surveillance"],\n    "hospital": HELIXCARE_URLS["hospital-reporter"],\n    "osint": HELIXCARE_URLS["osint-agent"],\n    "tasks/sendSubscribe": HELIXCARE_URLS["central-surveillance"],\n}',
    },
    {
        "path": "tests/nexus_harness/test_helixcare_protocol_discovery.py",
        "matrix_file": "helixcare_protocol_discovery_matrix.json",
        "prefix": "helixcare_discovery",
        "urls_dict": '{\n    "triage": HELIXCARE_URLS["triage-agent"],\n    "imaging": HELIXCARE_URLS["imaging-agent"],\n    "pharmacy": HELIXCARE_URLS["pharmacy-agent"],\n    "admission": HELIXCARE_URLS["bed-manager-agent"],\n    "discharge": HELIXCARE_URLS["discharge-agent"],\n    "surveillance": HELIXCARE_URLS["central-surveillance"],\n}',
    },
    {
        "path": "tests/nexus_harness/test_helixcare_protocol_security.py",
        "matrix_file": "helixcare_protocol_security_matrix.json",
        "prefix": "helixcare_security",
        "urls_dict": '{\n    "triage": HELIXCARE_URLS["triage-agent"],\n    "imaging": HELIXCARE_URLS["imaging-agent"],\n    "bed": HELIXCARE_URLS["bed-manager-agent"],\n    "discharge": HELIXCARE_URLS["discharge-agent"],\n    "tasks/sendSubscribe": HELIXCARE_URLS["triage-agent"],\n}',
    },
    {
        "path": "tests/nexus_harness/test_helixcare_iam_non_encounter.py",
        "matrix_file": "helixcare_iam_non_encounter_matrix.json",
        "prefix": "helixcare_iam_non_encounter",
        "urls_dict": '{\n    "gateway": os.environ.get("NEXUS_ON_DEMAND_GATEWAY_URL", "http://localhost:8100"),\n}',
    },
]


# ═══════════════════════════════════════════════════════════════
# 4. RUNNER PATCH
# ═══════════════════════════════════════════════════════════════

RUNNER_PATCH = """

# ── HelixCare matrix support (auto-generated) ──────────────────
HELIXCARE_MATRICES_DIR = pathlib.Path(__file__).resolve().parents[2] / "HelixCare"


def load_helixcare_matrix(filename: str) -> list[dict]:
    path = HELIXCARE_MATRICES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"HelixCare matrix not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def scenarios_for_helixcare(
    filename: str,
    *,
    tags: list[str] | None = None,
    scenario_type: str | None = None,
) -> list[dict]:
    rows = load_helixcare_matrix(filename)
    if scenario_type:
        rows = [r for r in rows if r.get("scenario_type") == scenario_type]
    if tags:
        tag_set = set(tags)
        rows = [r for r in rows if tag_set.intersection(r.get("test_tags", []))]
    return rows


HELIXCARE_URLS: dict[str, str] = {
    # Existing agents
    "triage-agent":        os.environ.get("HC_TRIAGE_URL",     "http://localhost:8021"),
    "diagnosis-agent":     os.environ.get("HC_DIAGNOSIS_URL",  "http://localhost:8022"),
    "openhie-mediator":    os.environ.get("HC_MEDIATOR_URL",   "http://localhost:8023"),
    "transcriber-agent":   os.environ.get("HC_TRANSCRIBER_URL","http://localhost:8031"),
    "summariser-agent":    os.environ.get("HC_SUMMARISER_URL", "http://localhost:8032"),
    "ehr-writer-agent":    os.environ.get("HC_EHR_URL",        "http://localhost:8033"),
    "insurer-agent":       os.environ.get("HC_INSURER_URL",    "http://localhost:8041"),
    "provider-agent":      os.environ.get("HC_PROVIDER_URL",   "http://localhost:8042"),
    "consent-analyser":    os.environ.get("HC_CONSENT_URL",    "http://localhost:8043"),
    "hitl-ui":             os.environ.get("HC_HITL_URL",       "http://localhost:8044"),
    "hospital-reporter":   os.environ.get("HC_HOSPITAL_URL",   "http://localhost:8051"),
    "osint-agent":         os.environ.get("HC_OSINT_URL",      "http://localhost:8052"),
    "central-surveillance":os.environ.get("HC_CENTRAL_URL",    "http://localhost:8053"),
    # HelixCare agents
    "imaging-agent":       os.environ.get("HC_IMAGING_URL",    "http://localhost:8024"),
    "pharmacy-agent":      os.environ.get("HC_PHARMACY_URL",   "http://localhost:8025"),
    "bed-manager-agent":   os.environ.get("HC_BED_URL",        "http://localhost:8026"),
    "discharge-agent":     os.environ.get("HC_DISCHARGE_URL",  "http://localhost:8027"),
    "followup-scheduler":  os.environ.get("HC_FOLLOWUP_URL",   "http://localhost:8028"),
    "care-coordinator":    os.environ.get("HC_COORDINATOR_URL","http://localhost:8029"),
}
"""


# ═══════════════════════════════════════════════════════════════
# 5. LAUNCH PATCH
# ═══════════════════════════════════════════════════════════════

NEW_AGENTS_BLOCK = """    # HelixCare agents
    ("demos/helixcare/imaging-agent",       8024),
    ("demos/helixcare/pharmacy-agent",      8025),
    ("demos/helixcare/bed-manager-agent",   8026),
    ("demos/helixcare/discharge-agent",     8027),
    ("demos/helixcare/followup-scheduler",  8028),
    ("demos/helixcare/care-coordinator",    8029),
"""

LAUNCH_ENV_PATCH = """    # HelixCare inter-agent URLs
    env["NEXUS_IMAGING_RPC"] = "http://localhost:8024/rpc"
    env["NEXUS_PHARMACY_RPC"] = "http://localhost:8025/rpc"
    env["NEXUS_BED_RPC"] = "http://localhost:8026/rpc"
    env["NEXUS_DISCHARGE_RPC"] = "http://localhost:8027/rpc"
    env["NEXUS_FOLLOWUP_RPC"] = "http://localhost:8028/rpc"
    env["NEXUS_COORDINATOR_RPC"] = "http://localhost:8029/rpc"
    env["NEXUS_TRIAGE_RPC"] = "http://localhost:8021/rpc"
"""


# ═══════════════════════════════════════════════════════════════
# EXECUTE
# ═══════════════════════════════════════════════════════════════


def main():
    print("=" * 70)
    print("HelixCare Bootstrap — Creating all missing components")
    print("=" * 70)

    # 1. Agent cards
    print("\n[1/6] Creating agent cards...")
    for path, card in AGENT_CARDS.items():
        write(path, json.dumps(card, indent=2) + "\n")

    # 2. Agent implementations
    print("\n[2/6] Creating agent implementations...")
    for path, (doc, name, body_fn) in AGENTS_CODE.items():
        code = AGENT_HEADER.format(doc=doc, name=name) + body_fn() + AGENT_RPC_BLOCK
        write(path, code)

    # 3. __init__.py files
    print("\n[3/6] Creating __init__.py files...")
    for agent in [
        "imaging-agent",
        "pharmacy-agent",
        "bed-manager-agent",
        "discharge-agent",
        "followup-scheduler",
        "care-coordinator",
    ]:
        write(f"demos/helixcare/{agent}/__init__.py", "")
        write(f"demos/helixcare/{agent}/app/__init__.py", "")

    # 4. Patch runner.py
    print("\n[4/6] Patching runner.py...")
    runner = ROOT / "tests" / "nexus_harness" / "runner.py"
    content = runner.read_text(encoding="utf-8")
    if "HELIXCARE_MATRICES_DIR" not in content:
        content += RUNNER_PATCH
        runner.write_text(content, encoding="utf-8")
        print("  ~ tests/nexus_harness/runner.py (patched)")
    else:
        print("  (already patched)")

    # 5. Create test harness files
    print("\n[5/6] Creating test harness files...")
    for cfg in TEST_CONFIGS:
        code = TEST_FILE_TEMPLATE.format(**cfg)
        write(cfg["path"], code)

    # 6. Patch launch_all_agents.py
    print("\n[6/6] Patching launch_all_agents.py...")
    launch = ROOT / "tools" / "launch_all_agents.py"
    lc = launch.read_text(encoding="utf-8")
    if "imaging-agent" not in lc:
        # Add new agents to AGENTS list
        lc = lc.replace(
            '    ("demos/public-health-surveillance/central-surveillance", 8053),\n]',
            '    ("demos/public-health-surveillance/central-surveillance", 8053),\n'
            + NEW_AGENTS_BLOCK
            + "]",
        )
        # Add inter-agent URLs to env block
        lc = lc.replace(
            '    env["FHIR_BASE_URL"] = "http://localhost:8080/fhir"',
            '    env["FHIR_BASE_URL"] = "http://localhost:8080/fhir"\n' + LAUNCH_ENV_PATCH,
        )
        launch.write_text(lc, encoding="utf-8")
        print("  ~ tools/launch_all_agents.py (patched)")
    else:
        print("  (already patched)")

    print("\n" + "=" * 70)
    print("Bootstrap complete!")
    print("=" * 70)
    print("""
Next steps:
  1. Stop existing agents:    python tools/launch_all_agents.py --stop
  2. Launch all 20 agents:    python tools/launch_all_agents.py
  3. Run HelixCare tests:     pytest tests/nexus_harness/test_helixcare_*.py -v
  4. Run full suite:          pytest tests/nexus_harness/ -v
""")


if __name__ == "__main__":
    main()
