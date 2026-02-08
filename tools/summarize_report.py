"""Summarize the conformance report."""
import json
from collections import Counter

r = json.load(open("C:/nexus-a2a-protocol/docs/conformance-report.json"))
print(f"Generated: {r['generated_at']}")
print(f"Total: {r['total']}  |  Passed: {r['passed']}  |  Failed: {r['failed']}  |  Skipped: {r['skipped']}  |  Errors: {r['errors']}")

demos = Counter()
demo_pass = Counter()
demo_fail = Counter()
demo_skip = Counter()
for s in r["results"]:
    d = s["poc_demo"]
    demos[d] += 1
    if s["status"] == "pass":
        demo_pass[d] += 1
    elif s["status"] == "fail":
        demo_fail[d] += 1
    elif s["status"] == "skip":
        demo_skip[d] += 1

print("\nBreakdown by PoC Demo:")
print(f"  {'Demo':<45} {'Total':>5} {'Pass':>5} {'Fail':>5} {'Skip':>5}")
print("  " + "-" * 65)
for d in sorted(demos):
    print(f"  {d:<45} {demos[d]:>5} {demo_pass[d]:>5} {demo_fail[d]:>5} {demo_skip[d]:>5}")

# Show fail reasons for first few
print("\nSample fail reasons:")
for s in r["results"]:
    if s["status"] == "fail" and s["message"]:
        print(f"  [{s['use_case_id']}] {s['message'][:100]}")
    if sum(1 for x in r["results"] if x["status"] == "fail" and x.get("message")) > 10:
        break
