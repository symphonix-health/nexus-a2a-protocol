#!/usr/bin/env python3
"""
Render Mermaid diagrams to SVG/PNG using the public Kroki API.

Usage:
    python scripts/render_mermaid_via_kroki.py docs/diagrams/*.mmd

Outputs will be written next to inputs as .svg and .png files.

Notes:
- Requires outbound internet access to https://kroki.io
- If offline, script will skip rendering and report which files were not processed.
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request

KROKI_SVG_URL = "https://kroki.io/mermaid/svg"
KROKI_PNG_URL = "https://kroki.io/mermaid/png"
TIMEOUT = 15


def render_one(input_path: str) -> tuple[bool, str]:
    base, _ = os.path.splitext(input_path)
    svg_out = base + ".svg"
    png_out = base + ".png"

    with open(input_path, encoding="utf-8") as f:
        source = f.read().encode("utf-8")

    for url, out_path in [(KROKI_SVG_URL, svg_out), (KROKI_PNG_URL, png_out)]:
        req = urllib.request.Request(url, data=source, method="POST")
        req.add_header("Content-Type", "text/plain; charset=utf-8")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                content = resp.read()
                with open(out_path, "wb") as out:
                    out.write(content)
        except urllib.error.URLError as exc:
            return False, f"kroki_error:{exc}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    return True, f"wrote {svg_out} and {png_out}"


def main():
    patterns = sys.argv[1:] or ["docs/diagrams/architecture-*.mmd"]
    files: list[str] = [
        p for p in patterns if os.path.splitext(p)[1] == ".mmd" and os.path.exists(p)
    ]
    if not files:
        print(
            "No .mmd files found. Pass explicit paths, e.g., "
            "docs/diagrams/architecture-high-level.mmd"
        )
        sys.exit(1)

    ok = 0
    for path in files:
        success, detail = render_one(path)
        status = "ok" if success else "fail"
        print(f"[{status}] {path} -> {detail}")
        if success:
            ok += 1

    if ok == 0:
        print("No diagrams rendered (network offline or kroki unavailable?)")
        sys.exit(2)


if __name__ == "__main__":
    main()
