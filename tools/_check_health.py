"""Check diagnosis agent health metrics."""
import httpx

h = httpx.get("http://localhost:8022/health", timeout=5)
m = h.json()["metrics"]
print(f"accepted={m['tasks_accepted']} completed={m['tasks_completed']} errored={m['tasks_errored']} avg_ms={m['avg_latency_ms']:.0f}")
print(f"Status: {h.json()['status']}")
