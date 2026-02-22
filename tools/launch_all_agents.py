"""Launch all NEXUS-A2A demo agents locally for testing.

Usage:
    python tools/launch_all_agents.py                    # start agents + backend
    python tools/launch_all_agents.py --no-backend       # start agents only
    python tools/launch_all_agents.py --backend-only     # start backend only (no agents)
    python tools/launch_all_agents.py --with-gateway     # also start on-demand gateway
    python tools/launch_all_agents.py --gateway-port 9000
                                                        # override gateway port (default 8100)
    python tools/launch_all_agents.py --only-gateway     # start only the gateway
                                                        # (no backend, no agents)
    python tools/launch_all_agents.py --llm-profile local_docker_smollm2
                                                        # start with a configured LLM profile
    python tools/launch_all_agents.py --list-llm-profiles
                                                        # show configured LLM profiles
    python tools/launch_all_agents.py --stop             # kill all
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

PYTHON = sys.executable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(ROOT, "config", "agents.json")
PID_FILE = os.path.join(ROOT, ".agent_pids.json")

GATEWAY_MODULE = "shared.on_demand_gateway.app.main:app"
GATEWAY_PORT = int(os.getenv("NEXUS_ON_DEMAND_GATEWAY_PORT", "8100"))


def load_agent_config():
    """Load agent configuration from centralized config file."""
    with open(CONFIG_FILE) as f:
        config = json.load(f)

    agents = []

    # Flatten agent hierarchy into (path, port, name, rpc_env) tuples
    for _category, category_agents in config.get("agents", {}).items():
        for agent_name, agent_info in category_agents.items():
            agents.append(
                (
                    agent_info["path"],
                    agent_info["port"],
                    agent_name,
                    agent_info.get("rpc_env"),
                    agent_info.get("env"),
                )
            )

    # Backend services (Command Centre)
    backend = []
    for service_name, service_info in config.get("backend", {}).items():
        backend.append((service_info["path"], service_info["port"], service_name))

    llm_profiles = config.get("llm_profiles", {})

    return agents, backend, llm_profiles


def apply_llm_profile(
    env: dict[str, str],
    llm_profiles: dict[str, dict],
    profile_name: str | None,
) -> str | None:
    """Apply a named LLM profile from config/agents.json into process env."""
    selected = profile_name or os.getenv("NEXUS_LLM_PROFILE")
    if not selected:
        return None

    profile = llm_profiles.get(selected)
    if not isinstance(profile, dict):
        available = ", ".join(sorted(llm_profiles.keys())) or "none"
        raise ValueError(f"Unknown LLM profile '{selected}'. Available: {available}")

    profile_env = profile.get("env", {})
    if not isinstance(profile_env, dict):
        raise ValueError(f"LLM profile '{selected}' has invalid 'env' configuration")

    for key, value in profile_env.items():
        env.setdefault(str(key), str(value))

    return selected


def print_llm_profiles(llm_profiles: dict[str, dict]) -> None:
    """Print configured LLM profiles."""
    if not llm_profiles:
        print("No llm_profiles configured in config/agents.json")
        return

    print("Configured LLM profiles:")
    for name, profile in llm_profiles.items():
        desc = ""
        if isinstance(profile, dict):
            desc = str(profile.get("description", "")).strip()
        print(f"  - {name}")
        if desc:
            print(f"    {desc}")


def probe_http_health(
    url: str,
    *,
    attempts: int,
    timeout_s: float,
    interval_s: float,
) -> tuple[bool, str]:
    """Probe an HTTP endpoint with bounded retries."""
    last_error = "unknown error"
    for attempt in range(1, attempts + 1):
        try:
            resp = urllib.request.urlopen(url, timeout=timeout_s)
            if 200 <= resp.status < 300:
                return True, f"status={resp.status}"
            last_error = f"status={resp.status}"
        except urllib.error.HTTPError as exc:
            last_error = f"status={exc.code}"
        except Exception as exc:  # noqa: BLE001 - launch-time diagnostics
            last_error = str(exc)

        if attempt < attempts:
            time.sleep(interval_s)

    return False, last_error


def _probe_http_once(url: str, timeout_s: float) -> tuple[bool, str]:
    """Single HTTP probe with compact diagnostics."""
    try:
        resp = urllib.request.urlopen(url, timeout=timeout_s)
        if 200 <= resp.status < 300:
            return True, f"status={resp.status}"
        return False, f"status={resp.status}"
    except urllib.error.HTTPError as exc:
        return False, f"status={exc.code}"
    except Exception as exc:  # noqa: BLE001 - launch-time diagnostics
        return False, str(exc)


def probe_backend_readiness(
    port: int,
    *,
    attempts: int,
    timeout_s: float,
    interval_s: float,
) -> tuple[bool, str]:
    """Probe backend readiness with endpoint fallback.

    Readiness preference order:
    1) /readyz (if implemented)
    2) /health + /api/agents (fallback for older backend builds)
    """
    base = f"http://localhost:{port}"
    last_error = "unknown error"

    for attempt in range(1, attempts + 1):
        ready_ok, ready_detail = _probe_http_once(f"{base}/readyz", timeout_s)
        if ready_ok:
            return True, f"readyz={ready_detail}"

        # Fallback path when /readyz is not available yet.
        if "status=404" in ready_detail:
            health_ok, health_detail = _probe_http_once(f"{base}/health", timeout_s)
            agents_ok, agents_detail = _probe_http_once(f"{base}/api/agents", timeout_s)
            if health_ok and agents_ok:
                return True, f"health={health_detail}, agents={agents_detail}"
            last_error = f"health={health_detail}, agents={agents_detail}"
        else:
            last_error = f"readyz={ready_detail}"

        if attempt < attempts:
            time.sleep(interval_s)

    return False, last_error


def start_gateway(env: dict[str, str], port: int | None = None) -> dict | dict[str, int] | None:
    """Start the on-demand gateway as a managed background process.

    Returns a PID entry dict on success, or ``None`` on failure.
    """
    # Allow override via CLI flag; otherwise use env/default
    gw_port = int(port or GATEWAY_PORT)

    # If a gateway is already running on the port, detect and reuse
    detected_ok, detected_detail = probe_http_health(
        f"http://localhost:{gw_port}/readyz", attempts=1, timeout_s=1.5, interval_s=0.2
    )
    if detected_ok:
        print(f"  [ok] On-demand Gateway :{gw_port} already running (readyz={detected_detail})")
        # Return a sentinel describing an existing (not managed) gateway
        return {"existing": True, "port": gw_port}

    cmd = [
        PYTHON,
        "-m",
        "uvicorn",
        GATEWAY_MODULE,
        "--host",
        "0.0.0.0",
        "--port",
        str(gw_port),
    ]
    # Optional: TLS/mTLS (same env contract as agents/backend)
    certfile = os.getenv("NEXUS_SSL_CERTFILE")
    keyfile = os.getenv("NEXUS_SSL_KEYFILE")
    ca_certs = os.getenv("NEXUS_SSL_CA_CERTS")
    cert_reqs_env = os.getenv("NEXUS_SSL_CERT_REQS", "none").lower()
    using_tls = False
    if certfile and keyfile:
        using_tls = True
        cmd += ["--ssl-certfile", certfile, "--ssl-keyfile", keyfile]
        if ca_certs:
            cmd += ["--ssl-ca-certs", ca_certs]
        if cert_reqs_env in ("required", "2"):
            cmd += ["--ssl-cert-reqs", "2"]
        elif cert_reqs_env in ("optional", "1"):
            cmd += ["--ssl-cert-reqs", "1"]
        elif cert_reqs_env in ("none", "0"):
            cmd += ["--ssl-cert-reqs", "0"]
    print(
        f"  Starting [GATEWAY] on-demand-gateway           :{gw_port} ...",
        end=" ",
        flush=True,
    )
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.0)
    if proc.poll() is not None:
        print(f"FAILED (exit {proc.returncode})")
        return None
    print(f"OK  (pid {proc.pid})")

    # Readiness probe
    gw_health_attempts = int(os.getenv("NEXUS_GATEWAY_HEALTHCHECK_ATTEMPTS", "15"))
    gw_health_timeout_s = float(os.getenv("NEXUS_GATEWAY_HEALTHCHECK_TIMEOUT_SECONDS", "3"))
    gw_health_interval_s = float(os.getenv("NEXUS_GATEWAY_HEALTHCHECK_INTERVAL_SECONDS", "1"))

    healthy, detail = probe_http_health(
        f"http://localhost:{gw_port}/readyz",
        attempts=gw_health_attempts,
        timeout_s=gw_health_timeout_s,
        interval_s=gw_health_interval_s,
    )
    if healthy:
        print(f"  [ok] Gateway :{gw_port} ready ({detail})")
    else:
        print(f"  [warn] Gateway :{gw_port} not ready yet ({detail})")

    return {
        "dir": "shared/on_demand_gateway",
        "port": gw_port,
        "pid": proc.pid,
        "type": "gateway",
        "ready": healthy,
        "ready_detail": detail,
        "scheme": "https" if using_tls else "http",
        "url": f"{'https' if using_tls else 'http'}://localhost:{gw_port}",
    }


def start_all(
    include_backend: bool = True,
    include_gateway: bool = False,
    llm_profile: str | None = None,
    *,
    start_agents: bool = True,
    gateway_port: int | None = None,
):
    """Start all agents and the backend Command Centre (default)."""
    agents, backend, llm_profiles = load_agent_config()

    env = os.environ.copy()
    env["PYTHONPATH"] = ROOT
    env.setdefault("NEXUS_JWT_SECRET", "dev-secret-change-me")
    env.setdefault("DID_VERIFY", "false")

    selected_profile = apply_llm_profile(env, llm_profiles, llm_profile)
    # Use provided test key/model only when neither the shell env nor profile set them.
    env.setdefault(
        "OPENAI_API_KEY",
        "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",
    )
    env.setdefault("OPENAI_MODEL", "gpt-4o-mini")
    if selected_profile:
        profile_meta = llm_profiles.get(selected_profile, {})
        profile_desc = ""
        if isinstance(profile_meta, dict):
            profile_desc = str(profile_meta.get("description", "")).strip()
        profile_note = f" ({profile_desc})" if profile_desc else ""
        print(f"Using LLM profile: {selected_profile}{profile_note}")
        print(f"  OPENAI_MODEL={env.get('OPENAI_MODEL', 'gpt-4o-mini')}")
        if "OPENAI_BASE_URL" in env:
            print(f"  OPENAI_BASE_URL={env['OPENAI_BASE_URL']}")
        else:
            print("  OPENAI_BASE_URL=https://api.openai.com/v1 (SDK default)")

    # Build environment variables for inter-agent communication
    for _rel_dir, port, _agent_name, rpc_env, env_name in agents:
        if rpc_env:
            env[rpc_env] = f"http://localhost:{port}/rpc"
        if env_name:
            env[env_name] = f"http://localhost:{port}"

    # Infrastructure
    env["MQTT_BROKER"] = "localhost"
    env["MQTT_PORT"] = "1883"
    env["FHIR_BASE_URL"] = "http://localhost:8080/fhir"
    env["REDIS_URL"] = "redis://localhost:6379"

    # Build AGENT_URLS for Command Centre (only agents, not backend itself)
    agent_urls = [f"http://localhost:{port}" for _, port, _, _, _ in agents]
    env["AGENT_URLS"] = ",".join(agent_urls)

    pids = []
    failed_starts = []
    services_to_start = []

    # Optionally start agents (default on)
    if start_agents:
        services_to_start.extend([(rel_dir, port, "agent") for rel_dir, port, _, _, _ in agents])

    # Optionally start backend
    if include_backend:
        services_to_start.extend([(rel_dir, port, "backend") for rel_dir, port, _ in backend])

    for rel_dir, port, service_type in services_to_start:
        agent_dir = os.path.join(ROOT, rel_dir)
        cmd = [
            PYTHON,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
            "--app-dir",
            ".",
        ]
        # Optional: scale with multiple workers
        workers = int(os.getenv("UVICORN_WORKERS", "1"))
        if workers and workers > 1:
            cmd += ["--workers", str(workers)]
        # Optional: TLS/mTLS
        certfile = os.getenv("NEXUS_SSL_CERTFILE")
        keyfile = os.getenv("NEXUS_SSL_KEYFILE")
        ca_certs = os.getenv("NEXUS_SSL_CA_CERTS")
        cert_reqs_env = os.getenv("NEXUS_SSL_CERT_REQS", "none").lower()
        if certfile and keyfile:
            cmd += ["--ssl-certfile", certfile, "--ssl-keyfile", keyfile]
            if ca_certs:
                cmd += ["--ssl-ca-certs", ca_certs]
            # Map common strings to ssl.CERT_* values used by uvicorn CLI
            if cert_reqs_env in ("required", "2"):
                cmd += ["--ssl-cert-reqs", "2"]
            elif cert_reqs_env in ("optional", "1"):
                cmd += ["--ssl-cert-reqs", "1"]
            elif cert_reqs_env in ("none", "0"):
                cmd += ["--ssl-cert-reqs", "0"]

        service_label = f"[{service_type.upper()}]" if service_type == "backend" else ""
        stderr_target = subprocess.DEVNULL if service_type == "backend" else subprocess.PIPE
        print(
            f"  Starting {service_label} {os.path.basename(rel_dir):30s}  :{port} ...",
            end=" ",
            flush=True,
        )
        proc = subprocess.Popen(
            cmd,
            cwd=agent_dir,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=stderr_target,
        )
        time.sleep(0.5)
        if proc.poll() is not None:
            err = ""
            if proc.stderr is not None:
                err = proc.stderr.read().decode(errors="replace")
            print(f"FAILED (exit {proc.returncode})")
            if err:
                print(f"    stderr: {err[:300]}")
            failed_starts.append(
                {
                    "dir": rel_dir,
                    "port": port,
                    "type": service_type,
                    "exit_code": proc.returncode,
                }
            )
        else:
            print(f"OK  (pid {proc.pid})")
            pids.append({"dir": rel_dir, "port": port, "pid": proc.pid, "type": service_type})

    # Optionally start on-demand gateway
    gateway_entry = None
    gateway_existing = False
    if include_gateway:
        gateway_entry = start_gateway(env, port=gateway_port)
        if gateway_entry and gateway_entry.get("existing"):
            gateway_existing = True
            # Do not append to pids; we don't manage this process
            gateway_entry = None
        if gateway_entry:
            pids.append(gateway_entry)

    with open(PID_FILE, "w") as f:
        json.dump(pids, f, indent=2)

    agent_count = sum(1 for p in pids if p.get("type") == "agent")
    backend_count = sum(1 for p in pids if p.get("type") == "backend")
    gateway_count = sum(1 for p in pids if p.get("type") == "gateway")
    # Only count the gateway in totals if it actually started
    total = len(services_to_start) + (1 if gateway_count else 0)

    service_summary = (
        f"\n{len(pids)}/{total} services started "
        f"({agent_count} agents, {backend_count} backend"
        + (f", {gateway_count} gateway" if gateway_count else "")
        + f"). PIDs saved to {PID_FILE}"
    )
    print(service_summary)

    # Effective configuration (easy copy-paste)
    backend_effective_url = None
    if include_backend:
        # Prefer an actually started backend entry if present
        backend_pids = [p for p in pids if p.get("type") == "backend"]
        if backend_pids:
            b_port = backend_pids[0].get("port")
            if b_port:
                b_scheme = (
                    "https"
                    if (os.getenv("NEXUS_SSL_CERTFILE") and os.getenv("NEXUS_SSL_KEYFILE"))
                    else "http"
                )
                backend_effective_url = f"{b_scheme}://localhost:{b_port}"

    gateway_effective_url = None
    if include_gateway:
        if gateway_entry and isinstance(gateway_entry, dict) and gateway_entry.get("url"):
            gateway_effective_url = str(gateway_entry.get("url"))
        elif gateway_existing:
            # Best-effort assumption for externally running gateway
            port_eff = gateway_port or GATEWAY_PORT
            gw_scheme = (
                "https"
                if (os.getenv("NEXUS_SSL_CERTFILE") and os.getenv("NEXUS_SSL_KEYFILE"))
                else "http"
            )
            gateway_effective_url = f"{gw_scheme}://localhost:{port_eff}"

    if backend_effective_url or gateway_effective_url or selected_profile:
        print("\nEffective configuration:")
        if backend_effective_url:
            print(f"  Backend URL: {backend_effective_url}")
        if gateway_effective_url:
            print(f"  Gateway URL: {gateway_effective_url}")
        profile_name = selected_profile or os.getenv("NEXUS_LLM_PROFILE")
        print(f"  Selected LLM profile: {profile_name or 'default'}")

    # Give agents a moment to bind
    print("Waiting 3s for agents to settle...")
    time.sleep(3)

    # Quick health check - ONLY for agents, not backend
    ok = 0
    agent_pids = [p for p in pids if p.get("type") == "agent"]

    for entry in agent_pids:
        url = f"http://localhost:{entry['port']}/.well-known/agent-card.json"
        try:
            resp = urllib.request.urlopen(url, timeout=3)
            if resp.status == 200:
                ok += 1
                print(f"  [ok] :{entry['port']} healthy")
            else:
                print(f"  [fail] :{entry['port']} status={resp.status}")
        except Exception as e:
            print(f"  [fail] :{entry['port']} {e}")

    print(f"\nAgent Health: {ok}/{len(agent_pids)} agents responding")

    # Check backend separately
    backend_pids = [p for p in pids if p.get("type") == "backend"]
    gateway_pids = [p for p in pids if p.get("type") == "gateway"]
    backend_failures = []
    backend_health_attempts = int(
        os.getenv(
            "NEXUS_BACKEND_HEALTHCHECK_ATTEMPTS",
            os.getenv("NEXUS_HEALTHCHECK_ATTEMPTS", "20"),
        )
    )
    backend_health_timeout_s = float(
        os.getenv(
            "NEXUS_BACKEND_HEALTHCHECK_TIMEOUT_SECONDS",
            os.getenv("NEXUS_HEALTHCHECK_TIMEOUT_SECONDS", "5"),
        )
    )
    backend_health_interval_s = float(
        os.getenv(
            "NEXUS_BACKEND_HEALTHCHECK_INTERVAL_SECONDS",
            os.getenv("NEXUS_HEALTHCHECK_INTERVAL_SECONDS", "1.5"),
        )
    )
    strict_backend_health = os.getenv("NEXUS_STRICT_BACKEND_HEALTHCHECK", "true").lower() not in {
        "0",
        "false",
        "no",
    }
    gateway_final_health_attempts = int(
        os.getenv(
            "NEXUS_GATEWAY_FINAL_HEALTHCHECK_ATTEMPTS",
            os.getenv("NEXUS_GATEWAY_HEALTHCHECK_ATTEMPTS", "15"),
        )
    )
    gateway_final_health_timeout_s = float(
        os.getenv(
            "NEXUS_GATEWAY_FINAL_HEALTHCHECK_TIMEOUT_SECONDS",
            os.getenv("NEXUS_GATEWAY_HEALTHCHECK_TIMEOUT_SECONDS", "3"),
        )
    )
    gateway_final_health_interval_s = float(
        os.getenv(
            "NEXUS_GATEWAY_FINAL_HEALTHCHECK_INTERVAL_SECONDS",
            os.getenv("NEXUS_GATEWAY_HEALTHCHECK_INTERVAL_SECONDS", "1"),
        )
    )

    if backend_pids:
        print("\nBackend Services:")
        for entry in backend_pids:
            healthy, detail = probe_backend_readiness(
                entry["port"],
                attempts=backend_health_attempts,
                timeout_s=backend_health_timeout_s,
                interval_s=backend_health_interval_s,
            )
            if healthy:
                print(f"  [ok] Command Centre :{entry['port']} running ({detail})")
            else:
                failure = f"Command Centre :{entry['port']} {detail}"
                backend_failures.append(failure)
                print(f"  [fail] {failure}")

    if include_gateway:
        print("\nGateway Services:")
        if not gateway_pids and not gateway_existing:
            backend_failures.append("On-demand Gateway failed to start")
            print("  [fail] On-demand Gateway failed to start")
        elif gateway_existing:
            # Existing gateway detected; already reported earlier
            pass
        else:
            for entry in gateway_pids:
                # Final readiness pass (important when gateway starts slowly)
                healthy_now, detail_now = probe_http_health(
                    f"http://localhost:{entry['port']}/readyz",
                    attempts=gateway_final_health_attempts,
                    timeout_s=gateway_final_health_timeout_s,
                    interval_s=gateway_final_health_interval_s,
                )
                entry["ready"] = healthy_now
                entry["ready_detail"] = detail_now

                if healthy_now:
                    print(
                        f"  [ok] On-demand Gateway :{entry['port']} running (readyz={detail_now})"
                    )
                else:
                    failure = f"On-demand Gateway :{entry['port']} readiness failed ({detail_now})"
                    backend_failures.append(failure)
                    print(f"  [fail] {failure}")

    if strict_backend_health and (include_backend or include_gateway):
        expected_backend_count = len(backend) if include_backend else 0
        expected_gateway_count = 0 if gateway_existing else (1 if include_gateway else 0)

        if len(backend_pids) < expected_backend_count:
            backend_failures.append(
                f"started backends={len(backend_pids)}/{expected_backend_count}"
            )
        if len(gateway_pids) < expected_gateway_count:
            backend_failures.append(
                f"started gateways={len(gateway_pids)}/{expected_gateway_count}"
            )

        managed_start_failures = [
            f"{entry['dir']}:{entry['port']} exit={entry['exit_code']}"
            for entry in failed_starts
            if entry.get("type") in {"backend", "gateway"}
        ]
        backend_failures.extend(managed_start_failures)

        if backend_failures:
            raise RuntimeError("Managed backend strict-fail: " + "; ".join(backend_failures))


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
    parser.add_argument("--stop", action="store_true", help="Stop all running services")
    parser.add_argument(
        "--with-backend",
        action="store_true",
        help="Deprecated flag; backend now starts by default.",
    )
    parser.add_argument(
        "--no-backend",
        action="store_true",
        help="Skip Command Centre backend startup.",
    )
    parser.add_argument(
        "--backend-only",
        action="store_true",
        help="Start only the Command Centre backend (no agents).",
    )
    parser.add_argument(
        "--with-gateway",
        action="store_true",
        help="Also launch the on-demand gateway on port 8100.",
    )
    parser.add_argument(
        "--only-gateway",
        action="store_true",
        help="Start only the on-demand gateway (no backend, no agents).",
    )
    parser.add_argument(
        "--gateway-port",
        type=int,
        help=(
            "Override the on-demand gateway port. "
            "Defaults to NEXUS_ON_DEMAND_GATEWAY_PORT env or 8100."
        ),
    )
    parser.add_argument("--llm-profile", help="Name of LLM profile from config/agents.json")
    parser.add_argument(
        "--list-llm-profiles",
        action="store_true",
        help="List available LLM profiles",
    )
    args = parser.parse_args()

    # Basic argument validation
    if args.backend_only and args.no_backend:
        print("Error: --backend-only and --no-backend are mutually exclusive")
        sys.exit(2)
    if args.only_gateway and args.backend_only:
        print("Error: --only-gateway and --backend-only are mutually exclusive")
        sys.exit(2)

    if args.stop:
        stop_all()
    elif args.list_llm_profiles:
        _, _, profiles = load_agent_config()
        print_llm_profiles(profiles)
    else:
        try:
            start_all(
                include_backend=(not args.no_backend) and (not args.only_gateway),
                include_gateway=(args.with_gateway or args.only_gateway),
                llm_profile=args.llm_profile,
                start_agents=(not args.backend_only) and (not args.only_gateway),
                gateway_port=args.gateway_port,
            )
        except ValueError as exc:
            print(f"Error: {exc}")
            sys.exit(2)
        except RuntimeError as exc:
            print(f"Error: {exc}")
            sys.exit(1)
