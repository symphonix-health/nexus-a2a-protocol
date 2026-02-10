#!/usr/bin/env python3
"""
HelixCare Requirements Coverage Analyzer
Reads all JSON matrices and extracts requirement IDs, scenario counts,
and coverage statistics.
"""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

MATRIX_DIR = Path(__file__).resolve().parent.parent / "HelixCare"

def load_matrix(filepath):
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)

def analyze():
    matrices = sorted(MATRIX_DIR.glob("helixcare_*.json"))
    
    all_req_ids = set()
    req_coverage = defaultdict(lambda: {
        "matrices": set(),
        "positive_count": 0,
        "negative_count": 0,
        "total_scenarios": 0,
    })
    
    matrix_stats = {}
    
    for mpath in matrices:
        name = mpath.stem
        scenarios = load_matrix(mpath)
        
        pos = sum(1 for s in scenarios if s.get("scenario_type") == "positive")
        neg = sum(1 for s in scenarios if s.get("scenario_type") == "negative")
        
        matrix_stats[name] = {
            "total": len(scenarios),
            "positive": pos,
            "negative": neg,
            "use_case_ids": [s["use_case_id"] for s in scenarios[:3]] + ["..."] if len(scenarios) > 3 else [s["use_case_id"] for s in scenarios],
        }
        
        for scenario in scenarios:
            for rid in scenario.get("requirement_ids", []):
                all_req_ids.add(rid)
                req_coverage[rid]["matrices"].add(name)
                req_coverage[rid]["total_scenarios"] += 1
                if scenario.get("scenario_type") == "positive":
                    req_coverage[rid]["positive_count"] += 1
                else:
                    req_coverage[rid]["negative_count"] += 1
    
    # Print summary
    print("=" * 80)
    print("HELIXCARE MATRIX SUMMARY")
    print("=" * 80)
    
    total_scenarios = 0
    for name, stats in sorted(matrix_stats.items()):
        total_scenarios += stats["total"]
        print(f"\n{name}:")
        print(f"  Total scenarios: {stats['total']}")
        print(f"  Positive: {stats['positive']}, Negative: {stats['negative']}")
        print(f"  Sample IDs: {stats['use_case_ids']}")
    
    print(f"\n{'=' * 80}")
    print(f"TOTAL SCENARIOS ACROSS ALL MATRICES: {total_scenarios}")
    print(f"UNIQUE REQUIREMENT IDs REFERENCED: {len(all_req_ids)}")
    print(f"{'=' * 80}")
    
    # Group requirements by prefix
    req_groups = defaultdict(list)
    for rid in sorted(all_req_ids):
        prefix = rid.rsplit("-", 1)[0]
        req_groups[prefix].append(rid)
    
    print("\nREQUIREMENT IDs BY CATEGORY:")
    for prefix, rids in sorted(req_groups.items()):
        ids_sorted = sorted(rids, key=lambda x: int(x.rsplit("-",1)[1]))
        print(f"  {prefix}: {', '.join(ids_sorted)}")
    
    # Coverage detail
    print(f"\n{'=' * 80}")
    print("REQUIREMENT COVERAGE DETAIL:")
    print(f"{'=' * 80}")
    print(f"{'Req ID':<10} {'Scenarios':>10} {'Positive':>10} {'Negative':>10} {'Matrices':>10}")
    print("-" * 60)
    
    for rid in sorted(all_req_ids, key=lambda x: (x.rsplit("-",1)[0], int(x.rsplit("-",1)[1]))):
        info = req_coverage[rid]
        print(f"{rid:<10} {info['total_scenarios']:>10} {info['positive_count']:>10} {info['negative_count']:>10} {len(info['matrices']):>10}")
    
    # Serializable output
    coverage_out = {}
    for rid in sorted(all_req_ids):
        info = req_coverage[rid]
        coverage_out[rid] = {
            "total_scenarios": info["total_scenarios"],
            "positive_count": info["positive_count"],
            "negative_count": info["negative_count"],
            "matrices": sorted(info["matrices"]),
        }
    
    outpath = MATRIX_DIR / "coverage_analysis.json"
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump({
            "matrix_stats": {k: {kk: vv for kk, vv in v.items() if kk != "use_case_ids"} for k, v in matrix_stats.items()},
            "total_scenarios": total_scenarios,
            "unique_requirements": len(all_req_ids),
            "requirement_ids": sorted(all_req_ids),
            "requirement_coverage": coverage_out,
        }, f, indent=2)
    
    print(f"\nCoverage analysis saved to {outpath}")

if __name__ == "__main__":
    analyze()
