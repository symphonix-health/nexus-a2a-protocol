"""Quick test runner for HelixCare comprehensive validation."""
import subprocess
import sys
import json
from pathlib import Path

def run_test_suite(test_module, max_scenarios=5):
    """Run a test module and capture results."""
    cmd = [
        sys.executable, "-m", "pytest",
        f"tests/nexus_harness/{test_module}",
        "-v", "--tb=line",
        f"-k", f"positive",  # Run positive scenarios only for speed
        "--maxfail=10"  # Stop after 10 failures
    ]
    
    print(f"\n{'='*70}")
    print(f"Running: {test_module}")
    print(f"{'='*70}")
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[:500])
    
    return result.returncode == 0

def main():
    """Run comprehensive HelixCare test suite."""
    test_modules = [
        "test_protocol_core.py",
        "test_ed_triage.py",
        "test_telemed_scribe.py",
        "test_consent_verification.py",
        "test_public_health_surveillance.py",
    ]
    
    results = {}
    for module in test_modules:
        try:
            passed = run_test_suite(module)
            results[module] = "PASS" if passed else "FAIL"
        except subprocess.TimeoutExpired:
            results[module] = "TIMEOUT"
        except Exception as e:
            results[module] = f"ERROR: {str(e)}"
    
    print(f"\n\n{'='*70}")
    print("HELIXCARE TEST SUITE SUMMARY")
    print(f"{'='*70}")
    for module, status in results.items():
        symbol = "✅" if status == "PASS" else "❌"
        print(f"{symbol} {module:50s} {status}")
    
    # Check conformance report
    report_path = Path("docs/conformance-report.json")
    if report_path.exists():
        with open(report_path) as f:
            report = json.load(f)
        print(f"\nConformance Report:")
        print(f"  Total: {report['total']}")
        print(f"  Passed: {report['passed']} ({report['passed']/report['total']*100:.1f}%)")
        print(f"  Failed: {report['failed']}")
        print(f"  Skipped: {report['skipped']}")

if __name__ == "__main__":
    main()
