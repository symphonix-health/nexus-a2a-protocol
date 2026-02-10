"""Generate requirement coverage summary from conformance-report.json.

Outputs a concise JSON summary at docs/conformance-coverage.json and prints a table.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

REPORT_PATH = Path("docs/conformance-report.json")
OUT_PATH = Path("docs/conformance-coverage.json")


def main() -> None:
    if not REPORT_PATH.exists():
        print(f"Report not found: {REPORT_PATH}")
        return

    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    by_req: dict[str, dict[str, int]] = defaultdict(lambda: {"pass": 0, "fail": 0, "skip": 0, "error": 0})

    for r in report.get("results", []):
        status = r.get("status", "error")
        for rid in r.get("requirement_ids", []) or ["UNSPECIFIED"]:
            if status == "pass":
                by_req[rid]["pass"] += 1
            elif status == "fail":
                by_req[rid]["fail"] += 1
            elif status == "skip":
                by_req[rid]["skip"] += 1
            else:
                by_req[rid]["error"] += 1

    # Aggregate totals
    total_reqs = len(by_req)
    fully_passed = sum(1 for v in by_req.values() if v["pass"] > 0 and v["fail"] == 0 and v["error"] == 0)

    summary = {
        "total_requirements": total_reqs,
        "fully_passed_requirements": fully_passed,
        "coverage_percent": (fully_passed / total_reqs * 100.0) if total_reqs else 0.0,
        "requirements": by_req,
    }

    OUT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Pretty-print top-line summary
    print("Requirement Coverage Summary")
    print(f"  Total requirements: {summary['total_requirements']}")
    print(f"  Fully passed:      {summary['fully_passed_requirements']} ({summary['coverage_percent']:.1f}%)")


if __name__ == "__main__":
    main()
