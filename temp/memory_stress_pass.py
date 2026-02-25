#!/usr/bin/env python3
"""Run a short stress pass and capture process memory curves.

Workload:
- dashboard poller (simulates open dashboard API activity)
- burst traffic phase
- sustained traffic phase

Outputs:
- CSV curve samples per second
- JSON summary with max/avg/p95 by phase and whole run
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

try:
    import psutil
except Exception as exc:  # pragma: no cover
    raise RuntimeError("psutil is required for memory curve capture") from exc


ROOT = Path(__file__).resolve().parents[1]
TRAFFIC_SCRIPT = ROOT / "tools" / "traffic_generator.py"


@dataclass
class PortPid:
    command_centre: int | None
    triage: int | None
    gateway: int | None


def _rss_mb(pid: int | None) -> float:
    if not pid:
        return float("nan")
    try:
        proc = psutil.Process(pid)
        return proc.memory_info().rss / (1024 * 1024)
    except Exception:
        return float("nan")


def _safe_p95(values: list[float]) -> float:
    v = [x for x in values if math.isfinite(x)]
    if not v:
        return float("nan")
    if len(v) == 1:
        return v[0]
    return statistics.quantiles(v, n=100, method="inclusive")[94]


def find_pid_by_port(port: int) -> int | None:
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status != psutil.CONN_LISTEN:
                continue
            if not conn.laddr:
                continue
            if int(conn.laddr.port) == int(port) and conn.pid:
                return int(conn.pid)
    except Exception:
        return None
    return None


async def ensure_service_ready(url: str, timeout_s: float = 20.0) -> None:
    start = time.time()
    async with httpx.AsyncClient(timeout=3.0) as client:
        while time.time() - start < timeout_s:
            try:
                response = await client.get(url)
                if response.status_code < 500:
                    return
            except Exception:
                pass
            await asyncio.sleep(0.5)
    raise RuntimeError(f"Service readiness probe failed: {url}")


async def dashboard_poller(stop_event: asyncio.Event) -> None:
    async with httpx.AsyncClient(timeout=4.0) as client:
        while not stop_event.is_set():
            for endpoint in ("/api/agents", "/api/topology", "/health"):
                try:
                    await client.get(f"http://localhost:8099{endpoint}")
                except Exception:
                    pass
            await asyncio.sleep(1.5)


async def run_traffic_phase(name: str, args: list[str]) -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", ".")
    cmd = [sys.executable, str(TRAFFIC_SCRIPT), *args]
    print(f"[phase] {name}: {' '.join(args)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(ROOT),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()
    if stdout:
        text = stdout.decode(errors="replace")
        print(text[-1200:])
    if stderr:
        text = stderr.decode(errors="replace")
        if text.strip():
            print(f"[phase:{name}:stderr] {text[-1200:]}")

    return int(proc.returncode or 0)


async def sample_memory_curves(
    stop_event: asyncio.Event,
    port_pids: PortPid,
    traffic_pid_getter,
    phase_getter,
    rows: list[dict[str, float | str]],
    sample_interval_s: float = 1.0,
) -> None:
    t0 = time.time()
    while not stop_event.is_set():
        python_procs = [
            p
            for p in psutil.process_iter(["pid", "name", "memory_info"])
            if p.info.get("name", "").lower().startswith("python")
        ]
        total_python_rss_mb = 0.0
        for p in python_procs:
            try:
                total_python_rss_mb += p.info["memory_info"].rss / (1024 * 1024)
            except Exception:
                continue

        traffic_pid = traffic_pid_getter()
        row = {
            "t_sec": round(time.time() - t0, 2),
            "phase": phase_getter(),
            "total_python_rss_mb": round(total_python_rss_mb, 3),
            "command_centre_rss_mb": round(_rss_mb(port_pids.command_centre), 3),
            "triage_rss_mb": round(_rss_mb(port_pids.triage), 3),
            "gateway_rss_mb": round(_rss_mb(port_pids.gateway), 3),
            "traffic_rss_mb": round(_rss_mb(traffic_pid), 3),
            "python_proc_count": len(python_procs),
        }
        rows.append(row)
        await asyncio.sleep(sample_interval_s)


def summarize(rows: list[dict[str, float | str]]) -> dict:
    phases = sorted({str(r["phase"]) for r in rows})

    def metrics_for(key: str, phase: str | None = None) -> dict[str, float]:
        if phase is None:
            vals = [float(r[key]) for r in rows if math.isfinite(float(r[key]))]
        else:
            vals = [
                float(r[key])
                for r in rows
                if str(r["phase"]) == phase and math.isfinite(float(r[key]))
            ]
        if not vals:
            return {"max": float("nan"), "avg": float("nan"), "p95": float("nan")}
        return {
            "max": round(max(vals), 3),
            "avg": round(statistics.fmean(vals), 3),
            "p95": round(_safe_p95(vals), 3),
        }

    keys = [
        "total_python_rss_mb",
        "command_centre_rss_mb",
        "triage_rss_mb",
        "gateway_rss_mb",
        "traffic_rss_mb",
    ]

    summary = {
        "overall": {k: metrics_for(k) for k in keys},
        "by_phase": {phase: {k: metrics_for(k, phase) for k in keys} for phase in phases},
        "samples": len(rows),
    }
    return summary


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--outdir", default=str(ROOT / "temp" / "memory_bench"))
    parser.add_argument("--burst-size", type=int, default=320)
    parser.add_argument("--burst-max-concurrent", type=int, default=120)
    parser.add_argument("--sustained-seconds", type=int, default=45)
    parser.add_argument("--sustained-rate", type=float, default=12.0)
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    await ensure_service_ready("http://localhost:8099/health")
    await ensure_service_ready("http://localhost:8021/health")

    port_pids = PortPid(
        command_centre=find_pid_by_port(8099),
        triage=find_pid_by_port(8021),
        gateway=find_pid_by_port(8100),
    )

    rows: list[dict[str, float | str]] = []
    stop_event = asyncio.Event()
    phase = "warmup"
    traffic_pid: int | None = None

    def _phase_getter() -> str:
        return phase

    def _traffic_pid_getter() -> int | None:
        return traffic_pid

    poller_task = asyncio.create_task(dashboard_poller(stop_event))
    sampler_task = asyncio.create_task(
        sample_memory_curves(
            stop_event,
            port_pids,
            _traffic_pid_getter,
            _phase_getter,
            rows,
            sample_interval_s=1.0,
        )
    )

    try:
        await asyncio.sleep(5)

        phase = "burst"
        burst_cmd = [
            "--mode",
            "burst",
            "--burst-size",
            str(args.burst_size),
            "--max-concurrent-tasks",
            str(args.burst_max_concurrent),
            "--deterministic",
            "--seed",
            "1729",
        ]
        burst_proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(TRAFFIC_SCRIPT),
            *burst_cmd,
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": "."},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        traffic_pid = int(burst_proc.pid)
        burst_stdout, burst_stderr = await burst_proc.communicate()
        if burst_stdout:
            print(burst_stdout.decode(errors="replace")[-1200:])
        if burst_stderr:
            txt = burst_stderr.decode(errors="replace")
            if txt.strip():
                print(f"[burst:stderr] {txt[-1200:]}")

        phase = "sustained"
        sustained_cmd = [
            "--mode",
            "sustained",
            "--duration",
            str(args.sustained_seconds),
            "--rate",
            str(args.sustained_rate),
            "--deterministic",
            "--seed",
            "1729",
            "--max-concurrent-tasks",
            str(args.burst_max_concurrent),
        ]
        sustained_proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(TRAFFIC_SCRIPT),
            *sustained_cmd,
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": "."},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        traffic_pid = int(sustained_proc.pid)
        sustained_stdout, sustained_stderr = await sustained_proc.communicate()
        if sustained_stdout:
            print(sustained_stdout.decode(errors="replace")[-1200:])
        if sustained_stderr:
            txt = sustained_stderr.decode(errors="replace")
            if txt.strip():
                print(f"[sustained:stderr] {txt[-1200:]}")

        phase = "cooldown"
        traffic_pid = None
        await asyncio.sleep(8)

    finally:
        stop_event.set()
        await asyncio.gather(poller_task, sampler_task, return_exceptions=True)

    csv_path = outdir / f"memory_curve_{args.label}.csv"
    json_path = outdir / f"memory_summary_{args.label}.json"

    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    payload = {
        "label": args.label,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ports": {
            "command_centre": 8099,
            "triage": 8021,
            "gateway": 8100,
        },
        "pids": {
            "command_centre": port_pids.command_centre,
            "triage": port_pids.triage,
            "gateway": port_pids.gateway,
        },
        "summary": summarize(rows),
        "csv": str(csv_path),
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"[done] curve={csv_path}")
    print(f"[done] summary={json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
