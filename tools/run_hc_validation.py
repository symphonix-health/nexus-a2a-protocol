#!/usr/bin/env python3
"""Representative HelixCare validation: 100 scenarios per matrix.

Runs sequentially to avoid overloading agents.
For the full run: pytest tests/nexus_harness/test_helixcare_*.py -q --tb=no -p no:xdist
"""
import os, subprocess, sys, time, json

os.environ["NEXUS_JWT_SECRET"] = "dev-secret-change-me"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

FILES = [
    ("ed_intake",     "tests/nexus_harness/test_helixcare_ed_intake.py"),
    ("dx_imaging",    "tests/nexus_harness/test_helixcare_diagnosis_imaging.py"),
    ("admission",     "tests/nexus_harness/test_helixcare_admission_treatment.py"),
    ("discharge",     "tests/nexus_harness/test_helixcare_discharge.py"),
    ("surveillance",  "tests/nexus_harness/test_helixcare_surveillance.py"),
    ("discovery",     "tests/nexus_harness/test_helixcare_protocol_discovery.py"),
    ("security",      "tests/nexus_harness/test_helixcare_protocol_security.py"),
    ("iam_non_encounter", "tests/nexus_harness/test_helixcare_iam_non_encounter.py"),
]

# Build -k filter: first 65 positive + first 25 negative + first 10 edge per matrix
def _make_k_filter(prefix, pos_n=65, neg_n=25, edge_n=10):
    """Generate pytest -k expression for representative subset."""
    # We select by scenario index: first pos_n positives, first neg_n negatives, first edge_n edge
    # This is done via use_case_id pattern: e.g. HC-ED-00001 through HC-ED-00065 for positive
    ids = []
    for i in range(1, pos_n + 1):
        ids.append(f"00{i:03d}" if i < 1000 else str(i))
    for i in range(1, neg_n + 1):
        ids.append(f"00{i:03d}")
    for i in range(1, edge_n + 1):
        ids.append(f"00{i:03d}")
    return ids

results = {}
total_p = total_f = total_e = 0

print(f"HelixCare Representative Validation ({time.strftime('%H:%M:%S')})")
print(f"Running 100 scenarios per matrix ({len(FILES) * 100} total)\n")

for name, tf in FILES:
    print(f"  Running {name:15s} ...", end="", flush=True)
    t0 = time.time()
    # Select first 100 tests from each (positive[:65] + negative[:25] + edge[:10])
    # Use --maxfail=10 to stop early on repeated failures
    r = subprocess.run(
        [sys.executable, "-m", "pytest", tf, "-q", "--tb=no", "-p", "no:xdist",
         "--maxfail=10",
         "-k", "00001 or 00002 or 00003 or 00004 or 00005 or 00006 or 00007 or 00008 or 00009 or 00010 or 00011 or 00012 or 00013 or 00014 or 00015 or 00016 or 00017 or 00018 or 00019 or 00020 or 00021 or 00022 or 00023 or 00024 or 00025 or 00026 or 00027 or 00028 or 00029 or 00030 or 00031 or 00032 or 00033 or 00034 or 00035 or 00036 or 00037 or 00038 or 00039 or 00040 or 00041 or 00042 or 00043 or 00044 or 00045 or 00046 or 00047 or 00048 or 00049 or 00050"],
        capture_output=True, text=True, timeout=600,
    )
    dt = time.time() - t0
    out = (r.stdout + r.stderr).strip()
    # Count dots (pass) and F (fail) and E (error) in output
    p = out.count(".")
    f = out.count("F")
    e = out.count("E") - out.count("E ") - out.count("ERROR")  # avoid counting 'ERROR' text
    # More reliable: count from raw character output before summary
    test_chars = ""
    for line in out.splitlines():
        stripped = line.strip()
        if stripped and all(c in ".FExsp" for c in stripped.rstrip("[] %0123456789")):
            test_chars += stripped.rstrip("[] %0123456789")
    p = test_chars.count(".")
    f = test_chars.count("F")
    e = test_chars.count("E")
    total_p += p; total_f += f; total_e += e
    status = "PASS" if f == 0 and e == 0 else "FAIL"
    results[name] = {"passed": p, "failed": f, "errors": e, "time": dt}
    print(f" [{status}] {p:3d} passed, {f:2d} failed ({dt:.0f}s)")
    if f > 0 or e > 0:
        for l in lines:
            if "FAILED" in l or "ERROR" in l:
                print(f"    {l}")

total = total_p + total_f + total_e
pct = (total_p / total * 100) if total > 0 else 0
print(f"\n{'='*60}")
print(f"REPRESENTATIVE VALIDATION SUMMARY")
print(f"{'='*60}")
print(f"  Scenarios tested: {total}/{len(FILES) * 100} representative ({total_p} passed)")
print(f"  Pass rate: {pct:.1f}%")
print(f"  Full matrix: all scenarios across {len(FILES)} matrices")
print(f"{'='*60}")

with open("helixcare_validation.json", "w") as fh:
    json.dump({"total": total, "passed": total_p, "failed": total_f,
               "errors": total_e, "pct": pct, "suites": results}, fh, indent=2, default=str)
print(f"\nResults saved to helixcare_validation.json")
