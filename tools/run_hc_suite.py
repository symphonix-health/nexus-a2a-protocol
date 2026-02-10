#!/usr/bin/env python3
"""Streamlined HelixCare test runner - writes results to helixcare_results.txt"""
import os, subprocess, sys, time

os.environ["NEXUS_JWT_SECRET"] = "dev-secret-change-me"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

FILES = [
    "tests/nexus_harness/test_helixcare_ed_intake.py",
    "tests/nexus_harness/test_helixcare_diagnosis_imaging.py",
    "tests/nexus_harness/test_helixcare_admission_treatment.py",
    "tests/nexus_harness/test_helixcare_discharge.py",
    "tests/nexus_harness/test_helixcare_surveillance.py",
    "tests/nexus_harness/test_helixcare_protocol_discovery.py",
    "tests/nexus_harness/test_helixcare_protocol_security.py",
]

out = open("helixcare_results.txt", "w")
def log(msg):
    print(msg, flush=True)
    out.write(msg + "\n")
    out.flush()

total_p = total_f = total_e = 0
for tf in FILES:
    name = os.path.basename(tf).replace(".py","")
    log(f"\n>>> {name}")
    t0 = time.time()
    r = subprocess.run([sys.executable, "-m", "pytest", tf, "-q", "--tb=no"],
                       capture_output=True, text=True, timeout=600)
    dt = time.time() - t0
    last = [l for l in (r.stdout+r.stderr).strip().splitlines() if l.strip()]
    summary = last[-1] if last else "?"
    p = f = e = 0
    for part in summary.replace(",", " ").split():
        try:
            n = int(part)
        except ValueError:
            if "passed" in part: p = n
            elif "failed" in part: f = n
            elif "error" in part: e = n
            n = 0
    total_p += p; total_f += f; total_e += e
    log(f"    {summary}  ({dt:.1f}s)")

log(f"\n{'='*50}")
log(f"TOTAL: {total_p} passed, {total_f} failed, {total_e} errors  ({total_p}/{total_p+total_f+total_e})")
log(f"{'='*50}")
out.close()
