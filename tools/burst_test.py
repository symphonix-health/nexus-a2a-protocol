#!/usr/bin/env python3
"""Quick burst test - sends 10 test tasks."""
import os
from shared.nexus_common.auth import mint_jwt

async def send_burst():
    secret = os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me")
    token = mint_jwt("burst-test", secret)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    complaints = ["chest pain", "headache", "fever", "abdominal pain", "shortness of breath"]
    
    async with httpx.AsyncClient() as client:
        tasks = []
        for i in range(10):
            payload = {
                "jsonrpc": "2.0",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "patient_ref": f"Patient/{random.randint(10000, 99999)}",
                        "inputs": {
                            "chief_complaint": random.choice(complaints),
                            "age": random.randint(20, 80),
                            "gender": random.choice(["male", "female"])
                        }
                    }
                },
                "id": f"burst-{i}"
            }
            tasks.append(client.post("http://localhost:8021/rpc", json=payload, headers=headers, timeout=60.0))
        
        print("Sending 10 tasks...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success = sum(1 for r in results if not isinstance(r, Exception) and r.status_code == 200)
        print(f"✓ {success}/10 tasks sent successfully")

if __name__ == "__main__":
    asyncio.run(send_burst())
