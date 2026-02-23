#!/usr/bin/env python3
"""Reset Command Centre trace store for clean rerun verification."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clear Command Centre trace store (in-memory + persisted file)."
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8099",
        help="Command Centre base URL (default: http://localhost:8099)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP timeout seconds (default: 10)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    target = f"{base_url}/api/traces"

    req = urllib.request.Request(
        target,
        method="DELETE",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            raw = resp.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"❌ Reset failed ({exc.code}): {detail}")
        return 1
    except Exception as exc:
        print(f"❌ Reset failed: {exc}")
        return 1

    cleared_count = int(payload.get("cleared_count", 0))
    print(f"✅ Trace store reset complete. Cleared {cleared_count} trace run(s).")
    print(f"   endpoint: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
