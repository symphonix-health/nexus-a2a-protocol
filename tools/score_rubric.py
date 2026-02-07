import argparse
import ast
import os
from typing import Tuple


def analyze_file(path: str) -> Tuple[bool, float]:
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)

    has_module_doc = ast.get_docstring(tree) is not None

    # Count annotated vs total function args + returns
    total = 0
    annotated = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Return annotation
            total += 1
            if node.returns is not None:
                annotated += 1
            # Arg annotations
            for arg in list(node.args.args) + list(node.args.kwonlyargs):
                total += 1
                if arg.annotation is not None:
                    annotated += 1
            if node.args.vararg is not None:
                total += 1
                if node.args.vararg.annotation is not None:
                    annotated += 1
            if node.args.kwarg is not None:
                total += 1
                if node.args.kwarg.annotation is not None:
                    annotated += 1

    coverage = (annotated / total) if total else 0.0
    return has_module_doc, coverage


def main():
    ap = argparse.ArgumentParser(description="Simple rubric: docstrings + type-hint coverage")
    ap.add_argument("--src", default="src", help="Folder to analyze")
    args = ap.parse_args()

    files = [f for f in os.listdir(args.src) if f.endswith(".py")]
    overall_doc = []
    coverages = []
    for f in files:
        has_doc, cov = analyze_file(os.path.join(args.src, f))
        overall_doc.append(has_doc)
        coverages.append(cov)
        print(f"{f}: docstring={'yes' if has_doc else 'no'}, type-hint-coverage={cov:.2f}")

    if files:
        avg_cov = sum(coverages) / len(coverages)
        doc_rate = sum(1 for d in overall_doc if d) / len(overall_doc)
        print(f"\nSummary: type-hint-coverage-avg={avg_cov:.2f}, module-doc-rate={doc_rate:.2f}")
    else:
        print("No .py files found to analyze.")


if __name__ == "__main__":
    main()
