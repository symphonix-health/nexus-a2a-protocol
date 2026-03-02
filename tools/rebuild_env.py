"""
Environment rebuild script for nexus-a2a-protocol.
Fixes version conflicts between FastAPI/Pydantic/Starlette.
"""

import os
import subprocess
import sys

VENV_PYTHON = r"C:\nexus-a2a-protocol\.venv\Scripts\python.exe"
VENV_PIP = r"C:\nexus-a2a-protocol\.venv\Scripts\pip.exe"
LOG = r"C:\nexus-a2a-protocol\env_rebuild.log"


def log(msg):
    print(msg)
    with open(LOG, "a") as f:
        f.write(msg + "\n")


def run(cmd, check=True):
    log(f">>> {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stdout.strip():
        log(result.stdout.strip())
    if result.stderr.strip():
        log(result.stderr.strip())
    if check and result.returncode != 0:
        log(f"FAILED (exit {result.returncode})")
    return result.returncode


def main():
    if os.path.exists(LOG):
        os.remove(LOG)

    log("=" * 60)
    log("STEP 1: Upgrade pip in existing venv")
    log("=" * 60)
    run(f'"{VENV_PYTHON}" -m pip install --upgrade pip', check=False)

    log("")
    log("=" * 60)
    log("STEP 2: Uninstall ALL conflicting packages")
    log("=" * 60)
    packages_to_remove = [
        "fastapi",
        "pydantic",
        "pydantic-core",
        "starlette",
        "uvicorn",
        "httptools",
        "anyio",
        "httpx",
        "annotated-doc",
        "typing-inspection",
    ]
    run(f'"{VENV_PIP}" uninstall -y {" ".join(packages_to_remove)}', check=False)

    # Clean up ghost directories
    site_packages = os.path.join(os.path.dirname(VENV_PIP), "..", "Lib", "site-packages")
    site_packages = os.path.normpath(site_packages)
    log(f"Checking for ghost dirs in {site_packages}...")
    import shutil

    for entry in os.listdir(site_packages):
        if entry.startswith("~") or entry.startswith("_"):
            ghost = os.path.join(site_packages, entry)
            if os.path.isdir(ghost) and entry.startswith("~"):
                log(f"  Removing ghost: {entry}")
                shutil.rmtree(ghost, ignore_errors=True)

    log("")
    log("=" * 60)
    log("STEP 3: Install pinned coherent dependency set")
    log("=" * 60)
    deps = [
        "fastapi==0.120.4",
        "pydantic==2.8.2",
        "uvicorn[standard]==0.30.6",
        "httpx==0.27.2",
        "websockets==12.0",
        "openai==1.40.6",
        "jinja2",
        "python-multipart",
        "pytest>=8.0",
        "pytest-asyncio>=0.21",
        "pytest-xdist",
        "ruff>=0.6",
        "pyyaml",
    ]
    rc = run(f'"{VENV_PIP}" install {" ".join(deps)}')
    if rc != 0:
        log("ERROR: pip install failed!")
        return 1

    log("")
    log("=" * 60)
    log("STEP 4: Install project in editable mode")
    log("=" * 60)
    run(f'"{VENV_PIP}" install -e C:\\nexus-a2a-protocol', check=False)

    log("")
    log("=" * 60)
    log("STEP 5: Verify imports")
    log("=" * 60)
    rc = run(
        f'"{VENV_PYTHON}" -c "from fastapi import FastAPI; import pydantic; print(f\'FastAPI+Pydantic {{pydantic.__version__}} OK\')"'
    )
    if rc != 0:
        log("FATAL: FastAPI import still broken!")
        return 1

    rc = run(
        f'"{VENV_PYTHON}" -c "from starlette.testclient import TestClient; print(\'TestClient OK\')"'
    )

    log("")
    log("=" * 60)
    log("STEP 6: Show final package versions")
    log("=" * 60)
    run(f'"{VENV_PIP}" list')

    log("")
    log("SUCCESS: Environment rebuilt cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
