#!/usr/bin/env python3
"""Long-running soak driver for memory trend analysis.

Runs sustained request traffic and samples RSS memory for monitored services.
Designed for 30-60 minute runs to expose memory growth regressions.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import random
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.nexus_common.auth import mint_jwt

CONFIG_FILE = ROOT / "config" / "agents.json"

COMPLAINTS = [
    "chest pain",
    "shortness of breath",
    "abdominal pain",
    "severe headache",
    "fever",
    "dizziness",
    "nausea and vomiting",
    "back pain",
    "palpitations",
    "syncope",
]


@dataclass(frozen=True)
class ServiceTarget:
    name: str
    kind: str
    port: int


@dataclass
class MemorySample:
    timestamp_iso: str
    elapsed_seconds: float
    service_name: str
    service_kind: str
    port: int
    pid: int | None
    process_name: str | None
    rss_bytes: int | None


@dataclass
class TrafficStats:
    batches_sent: int = 0
    requests_sent: int = 0
    responses_ok: int = 0
    responses_error: int = 0
    transport_errors: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run 30-60 minute memory soak test and export RSS trend reports."
    )
    parser.add_argument(
        "--duration-minutes",
        type=int,
        default=30,
        help="Soak duration in minutes (must be between 30 and 60).",
    )
    parser.add_argument(
        "--sample-interval-seconds",
        type=float,
        default=10.0,
        help="RSS sampling interval in seconds.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="Requests per traffic batch.",
    )
    parser.add_argument(
        "--batch-interval-seconds",
        type=float,
        default=3.0,
        help="Delay between traffic batches.",
    )
    parser.add_argument(
        "--gateway",
        default=os.getenv("NEXUS_ON_DEMAND_GATEWAY_URL", "").strip(),
        help="Optional gateway base URL (example: http://localhost:8100).",
    )
    parser.add_argument(
        "--triage-rpc-url",
        default="http://localhost:8021/rpc",
        help="Direct triage RPC URL when gateway is not provided.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "temp" / "soak_reports"),
        help="Directory to write soak report artifacts.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=35.0,
        help="HTTP timeout per request.",
    )
    parser.add_argument(
        "--gateway-port",
        type=int,
        default=int(os.getenv("NEXUS_ON_DEMAND_GATEWAY_PORT", "8100")),
        help="Gateway port to include in memory tracking when gateway is enabled.",
    )
    args = parser.parse_args()

    if args.duration_minutes < 30 or args.duration_minutes > 60:
        parser.error("--duration-minutes must be between 30 and 60")
    if args.sample_interval_seconds <= 0:
        parser.error("--sample-interval-seconds must be > 0")
    if args.batch_size <= 0:
        parser.error("--batch-size must be > 0")
    if args.batch_interval_seconds <= 0:
        parser.error("--batch-interval-seconds must be > 0")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be > 0")

    args.gateway = args.gateway.strip().rstrip("/")
    return args


def load_service_targets(include_gateway: bool, gateway_port: int) -> list[ServiceTarget]:
    if not CONFIG_FILE.is_file():
        raise RuntimeError(f"Missing config file: {CONFIG_FILE}")

    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    targets: list[ServiceTarget] = []
    agents = raw.get("agents", {})
    for category, group in agents.items():
        if not isinstance(group, dict):
            continue
        for key, info in group.items():
            if not isinstance(info, dict):
                continue
            port = info.get("port")
            if isinstance(port, int) and port > 0:
                targets.append(ServiceTarget(name=str(key), kind=str(category), port=port))

    backend = raw.get("backend", {})
    for key, info in backend.items():
        if not isinstance(info, dict):
            continue
        port = info.get("port")
        if isinstance(port, int) and port > 0:
            targets.append(ServiceTarget(name=str(key), kind="backend", port=port))

    if include_gateway:
        targets.append(ServiceTarget(name="on_demand_gateway", kind="gateway", port=gateway_port))

    unique: dict[int, ServiceTarget] = {}
    for target in targets:
        # Port is the stable disambiguator for sampled RSS in this stack.
        unique[target.port] = target
    return sorted(unique.values(), key=lambda t: (t.kind, t.port, t.name))


def scan_listening_pids_by_port() -> dict[int, int]:
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except Exception:
        return {}

    if result.returncode != 0:
        return {}

    out: dict[int, int] = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.startswith("TCP"):
            continue
        parts = re.split(r"\s+", line)
        if len(parts) < 5:
            continue
        local_addr = parts[1]
        state = parts[3].upper()
        pid_text = parts[4]
        if state != "LISTENING":
            continue
        try:
            port = int(local_addr.rsplit(":", 1)[-1])
            pid = int(pid_text)
        except Exception:
            continue
        out[port] = pid
    return out


def query_process_rss(pids: set[int]) -> dict[int, tuple[str, int]]:
    if not pids:
        return {}

    pid_list = ",".join(str(pid) for pid in sorted(pids))
    command = (
        f"$ids=@({pid_list}); "
        "Get-Process -Id $ids -ErrorAction SilentlyContinue | "
        "Select-Object Id,ProcessName,WS | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            check=False,
            timeout=12,
        )
    except Exception:
        return {}

    if result.returncode != 0:
        return {}

    raw = result.stdout.strip()
    if not raw:
        return {}

    try:
        payload = json.loads(raw)
    except Exception:
        return {}

    rows: list[dict[str, Any]]
    if isinstance(payload, list):
        rows = [row for row in payload if isinstance(row, dict)]
    elif isinstance(payload, dict):
        rows = [payload]
    else:
        rows = []

    out: dict[int, tuple[str, int]] = {}
    for row in rows:
        try:
            pid = int(row.get("Id"))
            name = str(row.get("ProcessName") or "")
            rss = int(row.get("WS") or 0)
        except Exception:
            continue
        out[pid] = (name, rss)
    return out


def build_rpc_target(gateway_url: str, triage_rpc_url: str) -> str:
    if gateway_url:
        return f"{gateway_url}/rpc/triage"
    return triage_rpc_url.rstrip("/")


def build_jsonrpc_payload(batch_idx: int, request_idx: int) -> dict[str, Any]:
    patient_num = random.randint(10000, 99999)
    return {
        "jsonrpc": "2.0",
        "id": f"soak-{batch_idx}-{request_idx}",
        "method": "tasks/sendSubscribe",
        "params": {
            "task": {
                "patient_ref": f"Patient/{patient_num}",
                "inputs": {
                    "chief_complaint": random.choice(COMPLAINTS),
                    "age": random.randint(18, 95),
                    "gender": random.choice(["male", "female"]),
                },
            }
        },
    }


async def run_traffic_loop(
    *,
    stop_event: asyncio.Event,
    stats: TrafficStats,
    target_rpc_url: str,
    batch_size: int,
    batch_interval_seconds: float,
    timeout_seconds: float,
) -> None:
    timeout = httpx.Timeout(timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        batch_idx = 0
        while not stop_event.is_set():
            token = mint_jwt("soak-memory", os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me"))
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            requests = [
                client.post(
                    target_rpc_url,
                    json=build_jsonrpc_payload(batch_idx, i),
                    headers=headers,
                )
                for i in range(batch_size)
            ]
            stats.batches_sent += 1
            stats.requests_sent += batch_size
            responses = await asyncio.gather(*requests, return_exceptions=True)
            for item in responses:
                if isinstance(item, Exception):
                    stats.transport_errors += 1
                    continue
                if 200 <= item.status_code < 300:
                    stats.responses_ok += 1
                else:
                    stats.responses_error += 1
            batch_idx += 1
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=batch_interval_seconds)
            except asyncio.TimeoutError:
                pass


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    idx = max(0, math.ceil((p / 100.0) * len(sorted_values)) - 1)
    idx = min(idx, len(sorted_values) - 1)
    return float(sorted_values[idx])


def write_reports(
    *,
    output_dir: Path,
    run_started_at: datetime,
    duration_minutes: int,
    sample_interval_seconds: float,
    target_rpc_url: str,
    samples: list[MemorySample],
    stats: TrafficStats,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "rss_timeseries.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "timestamp_iso",
                "elapsed_seconds",
                "service_name",
                "service_kind",
                "port",
                "pid",
                "process_name",
                "rss_bytes",
                "rss_mib",
            ]
        )
        for sample in samples:
            rss_mib = (sample.rss_bytes or 0) / (1024 * 1024) if sample.rss_bytes is not None else ""
            writer.writerow(
                [
                    sample.timestamp_iso,
                    f"{sample.elapsed_seconds:.3f}",
                    sample.service_name,
                    sample.service_kind,
                    sample.port,
                    sample.pid if sample.pid is not None else "",
                    sample.process_name or "",
                    sample.rss_bytes if sample.rss_bytes is not None else "",
                    f"{rss_mib:.3f}" if rss_mib != "" else "",
                ]
            )

    pid_csv_path = output_dir / "rss_by_pid_timeseries.csv"
    by_timestamp: dict[tuple[str, float], dict[int, tuple[str, int, list[str]]]] = {}
    for sample in samples:
        if sample.pid is None or sample.rss_bytes is None:
            continue
        key = (sample.timestamp_iso, sample.elapsed_seconds)
        slots = by_timestamp.setdefault(key, {})
        entry = slots.get(sample.pid)
        if entry is None:
            slots[sample.pid] = (
                sample.process_name or "",
                sample.rss_bytes,
                [sample.service_name],
            )
        else:
            name, rss, services = entry
            services.append(sample.service_name)
            # Same PID can own multiple monitored ports; keep max observed WS.
            slots[sample.pid] = (name, max(rss, sample.rss_bytes), services)

    with pid_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "timestamp_iso",
                "elapsed_seconds",
                "pid",
                "process_name",
                "rss_bytes",
                "rss_mib",
                "services",
            ]
        )
        for key in sorted(by_timestamp.keys(), key=lambda item: item[1]):
            timestamp_iso, elapsed_s = key
            for pid, (name, rss, services) in sorted(by_timestamp[key].items()):
                writer.writerow(
                    [
                        timestamp_iso,
                        f"{elapsed_s:.3f}",
                        pid,
                        name,
                        rss,
                        f"{rss / (1024 * 1024):.3f}",
                        ",".join(sorted(set(services))),
                    ]
                )

    service_values: dict[str, list[float]] = {}
    for sample in samples:
        if sample.rss_bytes is None:
            continue
        service_values.setdefault(sample.service_name, []).append(float(sample.rss_bytes))

    summary_rows: list[dict[str, Any]] = []
    for service_name, values in sorted(service_values.items()):
        start = values[0]
        end = values[-1]
        row = {
            "service_name": service_name,
            "samples": len(values),
            "start_rss_bytes": int(start),
            "end_rss_bytes": int(end),
            "delta_rss_bytes": int(end - start),
            "min_rss_bytes": int(min(values)),
            "max_rss_bytes": int(max(values)),
            "avg_rss_bytes": int(sum(values) / len(values)),
            "median_rss_bytes": int(median(values)),
            "p95_rss_bytes": int(percentile(values, 95)),
        }
        summary_rows.append(row)

    summary_rows.sort(key=lambda r: r["delta_rss_bytes"], reverse=True)

    traffic_summary = {
        "batches_sent": stats.batches_sent,
        "requests_sent": stats.requests_sent,
        "responses_ok": stats.responses_ok,
        "responses_error": stats.responses_error,
        "transport_errors": stats.transport_errors,
        "success_rate": (
            round((stats.responses_ok / stats.requests_sent) * 100.0, 2)
            if stats.requests_sent
            else 0.0
        ),
    }

    summary = {
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": datetime.now(timezone.utc).isoformat(),
        "duration_minutes": duration_minutes,
        "sample_interval_seconds": sample_interval_seconds,
        "target_rpc_url": target_rpc_url,
        "sample_count": len(samples),
        "traffic": traffic_summary,
        "services": summary_rows,
    }

    summary_json_path = output_dir / "summary.json"
    summary_json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    md_path = output_dir / "report.md"
    lines = [
        "# Memory Soak Report",
        "",
        f"- Run started: `{summary['run_started_at']}`",
        f"- Duration: `{duration_minutes} minutes`",
        f"- Sample interval: `{sample_interval_seconds}s`",
        f"- Target RPC: `{target_rpc_url}`",
        "",
        "## Traffic",
        "",
        f"- Requests sent: `{traffic_summary['requests_sent']}`",
        f"- Responses OK: `{traffic_summary['responses_ok']}`",
        f"- HTTP errors: `{traffic_summary['responses_error']}`",
        f"- Transport errors: `{traffic_summary['transport_errors']}`",
        f"- Success rate: `{traffic_summary['success_rate']}%`",
        "",
        "## Service RSS Summary",
        "",
        "| Service | Samples | Start MiB | End MiB | Delta MiB | Max MiB | P95 MiB |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        mib = 1024 * 1024
        lines.append(
            "| "
            f"{row['service_name']} | "
            f"{row['samples']} | "
            f"{row['start_rss_bytes'] / mib:.2f} | "
            f"{row['end_rss_bytes'] / mib:.2f} | "
            f"{row['delta_rss_bytes'] / mib:.2f} | "
            f"{row['max_rss_bytes'] / mib:.2f} | "
            f"{row['p95_rss_bytes'] / mib:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- Raw service RSS time series: `{csv_path}`",
            f"- Raw per-PID RSS time series: `{pid_csv_path}`",
            f"- JSON summary: `{summary_json_path}`",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "rss_csv": csv_path,
        "rss_pid_csv": pid_csv_path,
        "summary_json": summary_json_path,
        "report_md": md_path,
    }


async def run_soak(args: argparse.Namespace) -> dict[str, Path]:
    include_gateway = bool(args.gateway)
    targets = load_service_targets(include_gateway=include_gateway, gateway_port=args.gateway_port)
    target_rpc_url = build_rpc_target(args.gateway, args.triage_rpc_url)
    stop_event = asyncio.Event()
    traffic_stats = TrafficStats()
    samples: list[MemorySample] = []

    duration_seconds = args.duration_minutes * 60.0
    started_at = datetime.now(timezone.utc)
    start_monotonic = time.monotonic()
    print("Starting memory soak test")
    print(f"  Duration: {args.duration_minutes} minutes")
    print(f"  Sample interval: {args.sample_interval_seconds}s")
    print(f"  Traffic target: {target_rpc_url}")
    print(f"  Monitored services: {len(targets)}")

    traffic_task = asyncio.create_task(
        run_traffic_loop(
            stop_event=stop_event,
            stats=traffic_stats,
            target_rpc_url=target_rpc_url,
            batch_size=args.batch_size,
            batch_interval_seconds=args.batch_interval_seconds,
            timeout_seconds=args.timeout_seconds,
        )
    )

    next_log_time = 0.0
    try:
        while True:
            elapsed = time.monotonic() - start_monotonic
            if elapsed >= duration_seconds:
                break

            now_iso = datetime.now(timezone.utc).isoformat()
            port_to_pid = scan_listening_pids_by_port()
            pids = {port_to_pid[t.port] for t in targets if t.port in port_to_pid}
            pid_info = query_process_rss(pids)

            current_rows: list[MemorySample] = []
            for target in targets:
                pid = port_to_pid.get(target.port)
                process_name: str | None = None
                rss_bytes: int | None = None
                if pid is not None:
                    details = pid_info.get(pid)
                    if details is not None:
                        process_name, rss_bytes = details
                row = MemorySample(
                    timestamp_iso=now_iso,
                    elapsed_seconds=elapsed,
                    service_name=target.name,
                    service_kind=target.kind,
                    port=target.port,
                    pid=pid,
                    process_name=process_name,
                    rss_bytes=rss_bytes,
                )
                current_rows.append(row)
            samples.extend(current_rows)

            if elapsed >= next_log_time:
                top_running = [
                    row for row in current_rows if row.rss_bytes is not None and row.pid is not None
                ]
                top_running.sort(key=lambda row: row.rss_bytes or 0, reverse=True)
                top = top_running[:5]
                top_text = ", ".join(
                    f"{row.service_name}:{(row.rss_bytes or 0) / (1024 * 1024):.1f}MiB(pid={row.pid})"
                    for row in top
                ) or "no running services"
                print(
                    "["
                    f"{int(elapsed // 60):02d}:{int(elapsed % 60):02d}"
                    "] "
                    f"req={traffic_stats.requests_sent} ok={traffic_stats.responses_ok} "
                    f"err={traffic_stats.responses_error + traffic_stats.transport_errors} "
                    f"top={top_text}"
                )
                next_log_time = elapsed + 60.0

            await asyncio.sleep(args.sample_interval_seconds)
    finally:
        stop_event.set()
        try:
            await asyncio.wait_for(traffic_task, timeout=15.0)
        except Exception:
            traffic_task.cancel()

    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.output_dir) / f"soak_{run_stamp}"
    reports = write_reports(
        output_dir=out_dir,
        run_started_at=started_at,
        duration_minutes=args.duration_minutes,
        sample_interval_seconds=args.sample_interval_seconds,
        target_rpc_url=target_rpc_url,
        samples=samples,
        stats=traffic_stats,
    )
    return reports


def main() -> int:
    args = parse_args()
    try:
        reports = asyncio.run(run_soak(args))
    except KeyboardInterrupt:
        print("Soak interrupted by user")
        return 130
    except Exception as exc:
        print(f"Soak failed: {exc}")
        return 1

    print("Soak complete. Reports:")
    print(f"  Markdown: {reports['report_md']}")
    print(f"  Summary JSON: {reports['summary_json']}")
    print(f"  Service RSS CSV: {reports['rss_csv']}")
    print(f"  Per-PID RSS CSV: {reports['rss_pid_csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
