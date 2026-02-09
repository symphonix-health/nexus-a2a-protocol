#!/usr/bin/env python3
"""Simple traffic generator - sends realistic triage tasks continuously."""
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

import httpx

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.nexus_common.auth import mint_jwt

# Configuration
JWT_SECRET = os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me")
TOKEN = mint_jwt("traffic-gen", JWT_SECRET, ttl_seconds=3600)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Realistic chief complaints
COMPLAINTS = [
    "chest pain", "shortness of breath", "abdominal pain", "severe headache",
    "dizziness", "fever", "nausea and vomiting", "back pain",
    "difficulty breathing", "rapid heartbeat", "weakness", "confusion",
    "seizure", "allergic reaction", "trauma", "fall", "laceration"
]

async def send_task(client: httpx.AsyncClient, task_num: int):
    """Send a single triage task."""
    complaint = random.choice(COMPLAINTS)
    patient_id = f"Patient/{random.randint(10000, 99999)}"
    
    payload = {
        "jsonrpc": "2.0",
        "method": "tasks/sendSubscribe",
        "params": {
            "task": {
                "patient_ref": patient_id,
                "inputs": {
                    "chief_complaint": complaint,
                    "age": random.randint(18, 90),
                    "gender": random.choice(["male", "female"])
                }
            }
        },
        "id": f"task-{task_num}"
    }
    
    try:
        resp = await client.post(
            "http://localhost:8021/rpc",
            json=payload,
            headers=HEADERS,
            timeout=30.0
        )
        
        if resp.status_code == 200:
            result = resp.json()
            if "result" in result:
                return {"status": "ok", "task_id": result["result"].get("task_id")}
            else:
                return {"status": "error", "error": result.get("error")}
        else:
            return {"status": "fail", "code": resp.status_code}
    except Exception as e:
        return {"status": "exception", "error": str(e)}

async def main():
    """Generate continuous traffic."""
    print("🚀 Simple Traffic Generator")
    print("   Sending tasks to: http://localhost:8021/rpc")
    print("   Target rate: 5 tasks/second")
    print("   Press Ctrl+C to stop")
    print()
    
    sent = 0
    success = 0
    failed = 0
    start_time = time.time()
    
    async with httpx.AsyncClient() as client:
        try:
            while True:
                # Send task
                result = await send_task(client, sent + 1)
                sent += 1
                
                if result["status"] == "ok":
                    success += 1
                else:
                    failed += 1
                
                # Print progress
                elapsed = time.time() - start_time
                rate = sent / elapsed if elapsed > 0 else 0
                print(f"\r⏱️  {int(elapsed)}s | Sent: {sent} ({rate:.1f}/s) | "
                      f"✓ {success} | ✗ {failed}", end="", flush=True)
                
                # Rate limit to ~5 per second
                await asyncio.sleep(0.2)
                
        except KeyboardInterrupt:
            print("\n\n✅ Stopped")
            elapsed = time.time() - start_time
            print(f"\nFinal Stats:")
            print(f"  Tasks sent: {sent}")
            print(f"  Successful: {success}")
            print(f"  Failed: {failed}")
            print(f"  Duration: {elapsed:.1f}s")
            print(f"  Rate: {sent / elapsed:.2f} tasks/second")

if __name__ == "__main__":
    asyncio.run(main())
