from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_ROOTS = (
    ROOT / "src" / "nexus_a2a_protocol",
    ROOT / "shared" / "nexus_common",
)
FORBIDDEN_TOPLEVEL_IMPORTS = {"demos", "tests", "tools"}


def _iter_py_files(base: Path) -> list[Path]:
    return [p for p in base.rglob("*.py") if p.is_file()]


def _import_roots(py_file: Path) -> set[str]:
    roots: set[str] = set()
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                roots.add(root)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".", 1)[0]
                roots.add(root)
    return roots


def test_protocol_and_runtime_layers_do_not_depend_on_demo_or_test_code() -> None:
    violations: list[str] = []
    for base in PROTOCOL_ROOTS:
        for py_file in _iter_py_files(base):
            roots = _import_roots(py_file)
            bad = sorted(roots.intersection(FORBIDDEN_TOPLEVEL_IMPORTS))
            if bad:
                violations.append(f"{py_file.relative_to(ROOT)} -> {', '.join(bad)}")
    assert not violations, "Boundary violations found:\n" + "\n".join(violations)
