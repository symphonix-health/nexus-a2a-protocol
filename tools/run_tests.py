import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(description="Run pytest against a specific src folder")
    parser.add_argument("--src", default="src", help="Source folder containing modules under test")
    args = parser.parse_args()

    os.environ["SRC_PATH"] = args.src
    # Ensure src is importable first for tools that might import before tests set env
    sys.path.insert(0, os.path.abspath(args.src))

    try:
        import pytest  # type: ignore
    except Exception as e:
        print("pytest is required. Install with: pip install -e .", file=sys.stderr)
        raise e

    sys.exit(pytest.main(["-q"]))


if __name__ == "__main__":
    main()
