#!/usr/bin/env python3
"""Test connection to triage agent."""
import os
from shared.nexus_common.auth import mint_jwt

async def test():
    # Generate token
    secret = os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me")
    token = mint_jwt("test", secret)

    # Test payload
    payload = {
        "jsonrpc": "2.0",
        "method": "tasks/sendSubscribe",
        "params": {
            "task": {
                "patient_ref": "Patient/12345",
                "inputs": {
                    "chief_complaint": "chest pain",
                    "age": 45,
                    "gender": "male"
                }
            }
        },
        "id": "test1"
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    print("Sending test request to http://localhost:8021/rpc")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post("http://localhost:8021/rpc", json=payload, headers=headers, timeout=60.0)
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.json()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
