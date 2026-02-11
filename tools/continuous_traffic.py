#!/usr/bin/env python3
"""Continuous traffic generator - sends tasks in batches."""

import asyncio
import os
import random
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.nexus_common.auth import mint_jwt

COMPLAINTS = [
    "chest pain",
    "shortness of breath",
    "abdominal pain",
    "severe headache",
    "dizziness",
    "fever",
    "nausea and vomiting",
    "back pain",
    "difficulty breathing",
    "rapid heartbeat",
    "weakness",
    "confusion",
    "seizure",
    "allergic reaction",
    "trauma",
    "fall",
    "laceration",
    "bleeding",
    "burns",
    "fracture",
    "dehydration",
]


async def send_batch(num: int):
    """Send a batch of tasks."""
    secret = os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me")
    token = mint_jwt("continuous", secret)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        tasks = []
        for i in range(num):
            payload = {
                "jsonrpc": "2.0",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "patient_ref": f"Patient/{random.randint(10000, 99999)}",
                        "inputs": {
                            "chief_complaint": random.choice(COMPLAINTS),
                            "age": random.randint(18, 90),
                            "gender": random.choice(["male", "female"]),
                        },
                    }
                },
                "id": f"continuous-{i}",
            }
            tasks.append(
                client.post(
                    "http://localhost:8021/rpc", json=payload, headers=headers, timeout=60.0
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        success = sum(1 for r in results if not isinstance(r, Exception) and r.status_code == 200)
        return success, num


async def main():
    """Run continuous traffic."""
    total_sent = 0
    total_success = 0
    batch_size = 5
    batches = 0

    print("🚀 Starting continuous traffic generator...")
    print(f"📊 Batch size: {batch_size} tasks")
    print("⏱️  Interval: 3 seconds between batches")
    print("🎯 Target: Generate visible dashboard metrics\n")

    try:
        while batches < 100:  # Run 100 batches (500 tasks total over ~5 minutes)
            success, sent = await send_batch(batch_size)
            total_success += success
            total_sent += sent
            batches += 1

            rate = (total_success / total_sent * 100) if total_sent > 0 else 0
            print(
                f"Batch {batches:3d} | Sent: {total_sent:4d} | Success: {total_success:4d} ({rate:.1f}%)"
            )

            await asyncio.sleep(3)  # Wait 3 seconds between batches

    except KeyboardInterrupt:
        print("\n\n⏹️  Stopped by user")

    print(f"\n✅ Complete! Sent {total_sent} tasks, {total_success} successful")


if __name__ == "__main__":
    asyncio.run(main())
