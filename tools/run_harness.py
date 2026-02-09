"""Run the nexus harness tests and write results to harness_results.txt."""
import os
import sys
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PYTHON = os.path.join(ROOT, ".venv", "Scripts", "python.exe")

env = os.environ.copy()
env["PYTHONPATH"] = ROOT
env["NEXUS_JWT_SECRET"] = "dev-secret-change-me"

cmd = [
    VENV_PYTHON, "-m", "pytest",
    "tests/nexus_harness/",
    "--junitxml=harness_results.xml",
    "--override-ini=addopts=",
    "-v", "--tb=short",
]

print(f"Running: {' '.join(cmd)}")
print(f"CWD: {ROOT}")
t0 = time.time()

out_path = os.path.join(ROOT, "harness_output.txt")
with open(out_path, "w", encoding="utf-8") as f:
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        env=env,
        stdout=f,
        stderr=subprocess.STDOUT,
    )
    # Print heartbeat every 30s so terminal doesn't think we're idle
    while proc.poll() is None:
        elapsed = time.time() - t0
        print(f"  ... running ({elapsed:.0f}s elapsed)", flush=True)
        time.sleep(30)

elapsed = time.time() - t0
rc = proc.returncode
print(f"\nDone in {elapsed:.1f}s  |  Exit code: {rc}")
print(f"Results written to: {out_path}")

# Print the summary (last 20 lines)
with open(out_path, encoding="utf-8") as f:
    lines = f.readlines()
print(f"\n--- Last 30 lines of output ({len(lines)} total) ---")
for line in lines[-30:]:
    print(line, end="")
