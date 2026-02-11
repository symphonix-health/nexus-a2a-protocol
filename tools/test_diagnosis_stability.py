"""Quick stability test for the diagnosis agent."""
import httpx
import json
import time

TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJ0ZXN0LXVzZXIiLCJzY29wZSI6Im5leHVzOmludm9rZSIsImV4cCI6OTk5OTk5OTk5OX0."
    "9OlzIbA_TeCBCmRCbiB_VeENVvDxbeZWo5S2r_JGYfk"
)
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
URL = "http://localhost:8022/rpc"

ok = 0
for i in range(10):
    payload = {
        "jsonrpc": "2.0",
        "id": f"stress-{i}",
        "method": "tasks/sendSubscribe",
        "params": {"chief_complaint": f"test complaint {i}", "patient_ref": f"Patient/{i}"},
    }
    try:
        r = httpx.post(URL, json=payload, headers=HEADERS, timeout=10)
        data = r.json()
        if r.status_code == 200 and "result" in data:
            ok += 1
            print(f"  [{i}] OK - task_id={data['result']['task_id'][:20]}...")
        else:
            print(f"  [{i}] ERROR - {r.status_code}: {data}")
    except Exception as e:
        print(f"  [{i}] FAIL - {e}")
    time.sleep(0.3)

print(f"\nSent 10 requests, {ok} succeeded.")
print("Waiting 5s for background tasks...")
time.sleep(5)

# Health check
try:
    h = httpx.get("http://localhost:8022/health", timeout=5)
    m = h.json().get("metrics", {})
    status = h.json().get("status")
    print(f"\nHealth: {status}")
    print(f"  accepted={m.get('tasks_accepted')}")
    print(f"  completed={m.get('tasks_completed')}")
    print(f"  errored={m.get('tasks_errored')}")
    print(f"  avg_latency={m.get('avg_latency_ms'):.1f}ms")
except Exception as e:
    print(f"\nHealth FAILED: {e}")
