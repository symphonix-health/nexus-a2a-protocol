#!/usr/bin/env python3
"""Run all HelixCare test suites in parallel and collect results."""
import os, subprocess, sys, time, threading, json

os.environ["NEXUS_JWT_SECRET"] = "dev-secret-change-me"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

FILES = [
    ("ed_intake",          "tests/nexus_harness/test_helixcare_ed_intake.py"),
    ("dx_imaging",         "tests/nexus_harness/test_helixcare_diagnosis_imaging.py"),
    ("admission",          "tests/nexus_harness/test_helixcare_admission_treatment.py"),
    ("discharge",          "tests/nexus_harness/test_helixcare_discharge.py"),
    ("surveillance",       "tests/nexus_harness/test_helixcare_surveillance.py"),
    ("discovery",          "tests/nexus_harness/test_helixcare_protocol_discovery.py"),
    ("security",           "tests/nexus_harness/test_helixcare_protocol_security.py"),
    ("iam_non_encounter",  "tests/nexus_harness/test_helixcare_iam_non_encounter.py"),
]

results = {}
lock = threading.Lock()

def run_one(name, tf):
    t0 = time.time()
    r = subprocess.run(
        [sys.executable, "-m", "pytest", tf, "-q", "--tb=no", "-p", "no:xdist"],
        capture_output=True, text=True, timeout=1800,
    )
    dt = time.time() - t0
    out = (r.stdout + r.stderr).strip()
    lines = [l for l in out.splitlines() if l.strip()]
    summary = lines[-1] if lines else "?"
    p = f = e = 0
    prev = 0
    for part in summary.replace(",", " ").split():
        try:
            prev = int(part)
        except ValueError:
            if "passed" in part: p = prev
            elif "failed" in part: f = prev
            elif "error" in part: e = prev
            prev = 0
    with lock:
        results[name] = {"passed": p, "failed": f, "errors": e, "time": dt, "summary": summary, "rc": r.returncode}
        print(f"  [{name:15s}] done: {p} passed, {f} failed, {e} errors  ({dt:.0f}s)", flush=True)

print(f"Starting {len(FILES)} test suites in parallel ({time.strftime('%H:%M:%S')})")
threads = []
for name, tf in FILES:
    t = threading.Thread(target=run_one, args=(name, tf), name=name)
    threads.append(t)
    t.start()

for t in threads:
    t.join()

total_p = sum(r["passed"] for r in results.values())
total_f = sum(r["failed"] for r in results.values())
total_e = sum(r["errors"] for r in results.values())
total = total_p + total_f + total_e

print(f"\n{'='*60}")
print(f"HELIXCARE FULL SUITE RESULTS  ({time.strftime('%H:%M:%S')})")
print(f"{'='*60}")
for name, r in sorted(results.items()):
    ok = "PASS" if r["failed"] == 0 and r["errors"] == 0 else "FAIL"
    print(f"  [{ok}] {name:20s}  pass={r['passed']:4d}  fail={r['failed']:3d}  err={r['errors']:3d}  ({r['time']:.0f}s)")

pct = (total_p / total * 100) if total > 0 else 0
print(f"\n  TOTAL: {total_p}/{total} passed ({pct:.1f}%)")
print(f"  Target: full HelixCare matrix coverage across all configured suites")

# Save results
with open("helixcare_results.json", "w") as f:
    json.dump({"total_passed": total_p, "total_failed": total_f, "total_errors": total_e,
               "total": total, "pct": pct, "suites": results}, f, indent=2, default=str)
print(f"\nResults saved to helixcare_results.json")
