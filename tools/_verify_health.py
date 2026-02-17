"""Quick verification script for agent health fix."""

import time

import httpx
import jwt

token = jwt.encode(
    {"sub": "t", "scope": "nexus:invoke", "exp": int(time.time()) + 3600},
    "dev-secret-change-me",
    algorithm="HS256",
)
c = httpx.Client(timeout=30)
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# 1. Direct diagnosis/assess call
print("=== Direct diagnosis/assess ===")
r = c.post(
    "http://localhost:8022/rpc",
    json={
        "jsonrpc": "2.0",
        "id": "test1",
        "method": "diagnosis/assess",
        "params": {"task": {"chief_complaint": "headache"}},
    },
    headers=h,
)
resp = r.json()
print(f"  result={'result' in resp}  error={'error' in resp}")

time.sleep(2)
hh = c.get("http://localhost:8022/health").json()
m = hh["metrics"]
print(
    f"  Diagnosis health: status={hh['status']} "
    f"accepted={m['tasks_accepted']} completed={m['tasks_completed']} "
    f"errored={m['tasks_errored']}"
)

# 2. Triage tasks/sendSubscribe (fires background diagnosis call)
print("\n=== Triage tasks/sendSubscribe ===")
r2 = c.post(
    "http://localhost:8021/rpc",
    json={
        "jsonrpc": "2.0",
        "id": "test2",
        "method": "tasks/sendSubscribe",
        "params": {"task": {"chief_complaint": "headache", "patient": {"patient_id": "P1"}}},
    },
    headers=h,
)
resp2 = r2.json()
print(f"  result={'result' in resp2}  error={'error' in resp2}")

# Wait for background task to complete
time.sleep(8)

# 3. Check both agents
print("\n=== Final health status ===")
for port, name in [(8021, "triage"), (8022, "diagnosis")]:
    hh = c.get(f"http://localhost:{port}/health").json()
    m = hh["metrics"]
    print(
        f"  {name}: status={hh['status']} "
        f"accepted={m['tasks_accepted']} completed={m['tasks_completed']} "
        f"errored={m['tasks_errored']}"
    )

c.close()
