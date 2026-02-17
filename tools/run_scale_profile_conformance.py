#!/usr/bin/env python3
"""Run schema-level conformance checks for protocol v1.1 scale profile matrix."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nexus_a2a_protocol.jsonrpc import validate_envelope
from shared.nexus_common.jsonrpc import response_result
from shared.nexus_common.scale_profile import build_canonical_shard_key
from shared.nexus_common.sse import build_signed_resume_cursor, parse_signed_resume_cursor

MATRIX = ROOT / "nexus-a2a" / "artefacts" / "matrices" / "nexus_protocol_scale_profile_v1_1_matrix.json"
REPORT = ROOT / "docs" / "protocol_scale_profile_conformance.json"


def _run_g2_conflict_simulator() -> list[dict]:
    """Deterministic G2 conflict-policy simulator across region variants."""
    cases = [
        {
            "use_case_id": "UC-PROT-SCALE-G2-SIM-0001",
            "policy": "reject_on_conflict",
            "expected_version": "rv:expected-a",
            "current_version": "rv:current-a",
            "region_hint": "us-east-1",
            "region_served": "eu-west-1",
            "expect_error": True,
        },
        {
            "use_case_id": "UC-PROT-SCALE-G2-SIM-0002",
            "policy": "vector_clock",
            "expected_version": "rv:expected-b",
            "current_version": "rv:current-b",
            "region_hint": "us-east-1",
            "region_served": "ap-southeast-1",
            "expect_error": True,
        },
        {
            "use_case_id": "UC-PROT-SCALE-G2-SIM-0003",
            "policy": "last_write_wins",
            "expected_version": "rv:expected-c",
            "current_version": "rv:current-c",
            "region_hint": "us-east-1",
            "region_served": "us-west-2",
            "expect_error": False,
        },
    ]

    results: list[dict] = []
    for idx, case in enumerate(cases):
        task_key = f"task-g2-sim-{idx + 1}"
        scale_profile = {
            "profile": "nexus-scale-v1.1",
            "tenant_key": "tenant-g2-sim",
            "user_key": "user-g2-sim",
            "task_key": task_key,
            "shard_key": build_canonical_shard_key(
                tenant_key="tenant-g2-sim",
                user_key="user-g2-sim",
                task_key=task_key,
            ),
            "write_consistency": "global_quorum",
            "conflict_policy": case["policy"],
            "expected_version": case["expected_version"],
            "region_hint": case["region_hint"],
        }
        try:
            payload = response_result(
                f"g2-sim-{idx + 1}",
                {
                    "task_id": task_key,
                    "resource_version": case["current_version"],
                    "region_served": case["region_served"],
                },
                method="tasks/cancel",
                params={"scale_profile": scale_profile},
            )
            if case["expect_error"]:
                results.append(
                    {
                        "use_case_id": case["use_case_id"],
                        "status": "fail",
                        "message": "expected conflict error but received success",
                    }
                )
                continue

            result = payload.get("result", {})
            ok = (
                result.get("resource_version") == case["current_version"]
                and result.get("region_served") == case["region_served"]
                and result.get("consistency_applied") == "global_quorum"
            )
            results.append(
                {
                    "use_case_id": case["use_case_id"],
                    "status": "pass" if ok else "fail",
                    "message": "validated" if ok else "last_write_wins metadata mismatch",
                }
            )
        except Exception as exc:
            if not case["expect_error"]:
                results.append(
                    {
                        "use_case_id": case["use_case_id"],
                        "status": "fail",
                        "message": str(exc),
                    }
                )
                continue

            data = getattr(exc, "data", {}) or {}
            code = getattr(exc, "code", None)
            if case["policy"] == "reject_on_conflict":
                ok = (
                    code == -32000
                    and data.get("reason") == "conflict"
                    and data.get("conflict_policy") == "reject_on_conflict"
                )
                message = "validated" if ok else f"unexpected reject_on_conflict payload: {data}"
            elif case["policy"] == "vector_clock":
                competing = data.get("competing_versions")
                causality = data.get("causality")
                ok = (
                    code == -32000
                    and data.get("reason") == "conflict"
                    and data.get("conflict_policy") == "vector_clock"
                    and isinstance(competing, list)
                    and len(competing) >= 2
                    and isinstance(causality, dict)
                    and causality.get("policy") == "vector_clock"
                )
                message = "validated" if ok else f"unexpected vector_clock payload: {data}"
            else:
                ok = False
                message = f"unexpected failure for policy={case['policy']}: {exc}"

            results.append(
                {
                    "use_case_id": case["use_case_id"],
                    "status": "pass" if ok else "fail",
                    "message": message,
                }
            )

    return results


def _run_g2_failover_resume_simulator() -> list[dict]:
    """Deterministic G2 failover checks for cursor resume semantics."""
    cases = [
        {
            "use_case_id": "UC-PROT-SCALE-G2-SIM-FAILOVER-0001",
            "region_from": "us-east-1",
            "region_to": "eu-west-1",
            "stream_id": "task-g2-failover-1",
            "stream_epoch": "epoch-g2-1",
            "seq": 400,
            "issued_at_unix_ms": 1000,
            "retention_until_unix_ms": 4000,
            "exp_unix_ms": 5000,
            "now_unix_ms": 2000,
            "expect_error": False,
            "expected_resume_seq": 401,
        },
        {
            "use_case_id": "UC-PROT-SCALE-G2-SIM-FAILOVER-0002",
            "region_from": "us-east-1",
            "region_to": "eu-west-1",
            "stream_id": "task-g2-failover-2",
            "stream_epoch": "epoch-g2-2",
            "seq": 900,
            "issued_at_unix_ms": 1000,
            "retention_until_unix_ms": 1500,
            "exp_unix_ms": 5000,
            "now_unix_ms": 2000,
            "expect_error": True,
            "expected_error_contains": "retention",
        },
    ]

    results: list[dict] = []
    for case in cases:
        cursor = build_signed_resume_cursor(
            stream_id=case["stream_id"],
            stream_epoch=case["stream_epoch"],
            seq=case["seq"],
            exp_unix_ms=case["exp_unix_ms"],
            issued_at_unix_ms=case["issued_at_unix_ms"],
            retention_until_unix_ms=case["retention_until_unix_ms"],
            cursor_secret="g2-failover-secret",
        )
        try:
            parsed = parse_signed_resume_cursor(
                cursor,
                cursor_secret="g2-failover-secret",
                now_unix_ms=case["now_unix_ms"],
            )
            if case["expect_error"]:
                results.append(
                    {
                        "use_case_id": case["use_case_id"],
                        "status": "fail",
                        "message": (
                            "expected failover parse error but got success "
                            f"{case['region_from']}->{case['region_to']}"
                        ),
                    }
                )
                continue

            resume_from_seq = int(parsed["seq"]) + 1
            ok = (
                parsed.get("stream_id") == case["stream_id"]
                and parsed.get("stream_epoch") == case["stream_epoch"]
                and resume_from_seq == case["expected_resume_seq"]
            )
            results.append(
                {
                    "use_case_id": case["use_case_id"],
                    "status": "pass" if ok else "fail",
                    "message": (
                        "validated"
                        if ok
                        else (
                            "failover resume mismatch: "
                            f"{case['region_from']}->{case['region_to']} "
                            f"resume={resume_from_seq}"
                        )
                    ),
                }
            )
        except Exception as exc:  # noqa: BLE001 - deterministic gate mapping
            if not case["expect_error"]:
                results.append(
                    {
                        "use_case_id": case["use_case_id"],
                        "status": "fail",
                        "message": str(exc),
                    }
                )
                continue

            detail = str(exc).lower()
            token = str(case["expected_error_contains"]).lower()
            ok = token in detail
            results.append(
                {
                    "use_case_id": case["use_case_id"],
                    "status": "pass" if ok else "fail",
                    "message": "validated" if ok else f"unexpected failover error: {exc}",
                }
            )

    return results


def main() -> int:
    os.environ.setdefault("NEXUS_SCALE_PROFILE_STRICT", "true")
    rows = json.loads(MATRIX.read_text(encoding="utf-8"))

    passed = 0
    failed = 0
    results: list[dict] = []
    for row in rows:
        case_id = row.get("use_case_id", "unknown")
        payload = row.get("input_payload", {})
        scenario_type = row.get("scenario_type", "positive")
        try:
            validate_envelope(payload)
            ok = scenario_type != "negative"
            results.append(
                {
                    "use_case_id": case_id,
                    "status": "pass" if ok else "fail",
                    "message": "validated" if ok else "expected validation failure but passed",
                }
            )
            if ok:
                passed += 1
            else:
                failed += 1
        except Exception as exc:
            ok = scenario_type == "negative"
            results.append(
                {
                    "use_case_id": case_id,
                    "status": "pass" if ok else "fail",
                    "message": str(exc),
                }
            )
            if ok:
                passed += 1
            else:
                failed += 1

    g2_results = _run_g2_conflict_simulator()
    for item in g2_results:
        results.append(item)
        if item.get("status") == "pass":
            passed += 1
        else:
            failed += 1

    g2_failover_results = _run_g2_failover_resume_simulator()
    for item in g2_failover_results:
        results.append(item)
        if item.get("status") == "pass":
            passed += 1
        else:
            failed += 1

    report = {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "pass_rate_pct": round((passed / len(results)) * 100, 2) if results else 0.0,
        "results": results,
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"Scale profile conformance: total={report['total']} "
        f"passed={report['passed']} failed={report['failed']}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
