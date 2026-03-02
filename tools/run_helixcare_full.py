#!/usr/bin/env python3
"""Run all HelixCare test suites and report results."""
import os
import subprocess
import sys
import time

os.environ["NEXUS_JWT_SECRET"] = "dev-secret-change-me"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

TEST_FILES = [
    "tests/nexus_harness/test_helixcare_ed_intake.py",
    "tests/nexus_harness/test_helixcare_diagnosis_imaging.py",
    "tests/nexus_harness/test_helixcare_admission_treatment.py",
    "tests/nexus_harness/test_helixcare_discharge.py",
    "tests/nexus_harness/test_helixcare_surveillance.py",
    "tests/nexus_harness/test_helixcare_protocol_discovery.py",
    "tests/nexus_harness/test_helixcare_protocol_security.py",
    "tests/nexus_harness/test_helixcare_iam_non_encounter.py",
]

results = {}
total_pass = 0
total_fail = 0
total_err = 0

for tf in TEST_FILES:
    name = os.path.basename(tf).replace("test_helixcare_", "").replace(".py", "")
    print(f"\n{'='*60}")
    print(f"Running: {name}")
    print(f"{'='*60}", flush=True)
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", tf, "-q", "--tb=line"],
        capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=600,
    )
    elapsed = time.time() - t0
    output = proc.stdout + proc.stderr
    lines = [l.strip() for l in output.strip().splitlines() if l.strip()]
    summary = lines[-1] if lines else "no output"
    passed = failed = errors = 0
    for part in summary.split(","):
        part = part.strip()
        if "passed" in part:
            try: passed = int(part.split()[0])
            except: pass
        elif "failed" in part:
            try: failed = int(part.split()[0])
            except: pass
        elif "error" in part:
            try: errors = int(part.split()[0])
            except: pass
    total_pass += passed
    total_fail += failed
    total_err += errors
    results[name] = {"passed": passed, "failed": failed, "errors": errors,
                      "time": f"{elapsed:.1f}s", "summary": summary}
    print(f"  Result: {summary}")
    print(f"  Time: {elapsed:.1f}s", flush=True)
    if failed > 0 or errors > 0:
        fail_lines = [l for l in output.splitlines() if "FAILED" in l or "ERROR" in l]
        for fl in fail_lines[:5]:
            print(f"  {fl}")

print(f"\n{'='*60}")
print("HELIXCARE TEST SUITE SUMMARY")
print(f"{'='*60}")
for name, r in results.items():
    status = "PASS" if r["failed"] == 0 and r["errors"] == 0 else "FAIL"
    print(f"  [{status}] {name:30s}  pass={r['passed']:4d}  fail={r['failed']:3d}  err={r['errors']:3d}  {r['time']}")

total = total_pass + total_fail + total_err
pct = (total_pass / total * 100) if total > 0 else 0
print(f"\n  TOTAL: {total_pass}/{total} passed ({pct:.1f}%)  |  {total_fail} failed  |  {total_err} errors")
print(f"  Target: full HelixCare matrix coverage across all configured suites")
