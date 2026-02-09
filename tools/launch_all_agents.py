"""Launch all NEXUS-A2A demo agents locally for testing.

Usage:
    python tools/launch_all_agents.py          # start all
    python tools/launch_all_agents.py --stop   # kill all
"""
from __future__ import annotations

import os
import sys
import signal
import subprocess
import time
import argparse
import json

PYTHON = sys.executable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# agent_dir (relative to ROOT), port
AGENTS = [
    # ED Triage
    ("demos/ed-triage/openhie-mediator",        8023),
    ("demos/ed-triage/diagnosis-agent",         8022),
    ("demos/ed-triage/triage-agent",            8021),
    # Telemed Scribe
    ("demos/telemed-scribe/ehr-writer-agent",   8033),
    ("demos/telemed-scribe/summariser-agent",   8032),
    ("demos/telemed-scribe/transcriber-agent",  8031),
    # Consent Verification
    ("demos/consent-verification/consent-analyser", 8043),
    ("demos/consent-verification/hitl-ui",          8044),
    ("demos/consent-verification/provider-agent",   8042),
    ("demos/consent-verification/insurer-agent",    8041),
    # Public Health Surveillance
    ("demos/public-health-surveillance/hospital-reporter",    8051),
    ("demos/public-health-surveillance/osint-agent",          8052),
    ("demos/public-health-surveillance/central-surveillance", 8053),
]

PID_FILE = os.path.join(ROOT, ".agent_pids.json")


def start_all():
    env = os.environ.copy()
    env["PYTHONPATH"] = ROOT
    env.setdefault("NEXUS_JWT_SECRET", "dev-secret-change-me")
    env.setdefault("DID_VERIFY", "false")
    # Use provided test key if no specific key is set in environment
    env.setdefault("OPENAI_API_KEY", "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")
    # Inter-agent URLs for orchestrators
    env["NEXUS_DIAGNOSIS_RPC"] = "http://localhost:8022/rpc"
    env["NEXUS_OPENHIE_RPC"] = "http://localhost:8023/rpc"
    env["HOSPITAL_REPORTER_URL"] = "http://localhost:8051"
    env["OSINT_AGENT_URL"] = "http://localhost:8052"
    env["MQTT_BROKER"] = "localhost"
    env["MQTT_PORT"] = "1883"
    env["FHIR_BASE_URL"] = "http://localhost:8080/fhir"

    pids = []

    # Start Mock FHIR Server
    # cmd_fhir = [PYTHON, "tools/mock_fhir.py"]
    # print(f"  Starting Mock FHIR Server      :8080 ...", end=" ", flush=True)
    # proc_fhir = subprocess.Popen(
    #     cmd_fhir,
    #     cwd=ROOT,
    #     env=env,
    #     stdout=subprocess.DEVNULL,
    #     stderr=subprocess.PIPE,
    # )
    # print(f"OK  (pid {proc_fhir.pid})")
    # pids.append({"dir": "tools/mock_fhir.py", "port": 8080, "pid": proc_fhir.pid})
    # time.sleep(1)

    for rel_dir, port in AGENTS:
        agent_dir = os.path.join(ROOT, rel_dir)
        cmd = [
            PYTHON, "-m", "uvicorn",
            "app.main:app",
            "--host", "0.0.0.0",
            "--port", str(port),
            "--app-dir", ".",
        ]
        print(f"  Starting {os.path.basename(rel_dir):30s}  :{port} ...", end=" ", flush=True)
        proc = subprocess.Popen(
            cmd,
            cwd=agent_dir,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        time.sleep(0.5)
        if proc.poll() is not None:
            err = proc.stderr.read().decode(errors="replace")
            print(f"FAILED (exit {proc.returncode})")
            print(f"    stderr: {err[:300]}")
        else:
            print(f"OK  (pid {proc.pid})")
            pids.append({"dir": rel_dir, "port": port, "pid": proc.pid})

    with open(PID_FILE, "w") as f:
        json.dump(pids, f, indent=2)
    print(f"\n{len(pids)}/{len(AGENTS)} agents started.  PIDs saved to {PID_FILE}")

    # Give agents a moment to bind
    print("Waiting 3s for agents to settle...")
    time.sleep(3)

    # Quick health check
    import urllib.request
    ok = 0
    for entry in pids:
        url = f"http://localhost:{entry['port']}/.well-known/agent-card.json"
        try:
            resp = urllib.request.urlopen(url, timeout=3)
            if resp.status == 200:
                ok += 1
                print(f"  ✓ :{entry['port']} healthy")
            else:
                print(f"  ✗ :{entry['port']} status={resp.status}")
        except Exception as e:
            print(f"  ✗ :{entry['port']} {e}")
    print(f"\nHealth: {ok}/{len(pids)} agents responding")


def stop_all():
    if not os.path.exists(PID_FILE):
        print("No PID file found.")
        return
    with open(PID_FILE) as f:
        pids = json.load(f)
    for entry in pids:
        try:
            os.kill(entry["pid"], signal.SIGTERM)
            print(f"  Killed {entry['dir']} (pid {entry['pid']})")
        except (ProcessLookupError, OSError):
            print(f"  Already gone: {entry['dir']} (pid {entry['pid']})")
    os.remove(PID_FILE)
    print("All agents stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    if args.stop:
        stop_all()
    else:
        start_all()
