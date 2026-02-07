import argparse
import os
import time
from pathlib import Path
from typing import Dict, Any

import yaml
from rich import print


SYSTEM_INSTRUCTIONS = (
    "You are an expert Python developer. Given a task, output ONLY the code for the specified file. "
    "No explanations, no markdown fences. Use type hints and include a concise module-level docstring."
)


def load_tasks(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data


def load_env_if_present():
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def ensure_client():
    load_env_if_present()
    # Prefer Azure OpenAI if configured; otherwise fallback to OpenAI
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_key = os.getenv("AZURE_OPENAI_KEY")
    azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")

    if azure_endpoint and azure_key and azure_deployment:
        try:
            from openai import AzureOpenAI  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "openai>=1.12.0 is required. Install with: pip install -e ."
            ) from e

        client = AzureOpenAI(
            api_key=azure_key,
            api_version="2024-08-01-preview",
            azure_endpoint=azure_endpoint,
        )
        return ("azure", client, azure_deployment)

    # OpenAI path
    openai_key = os.getenv("OPENAI_API_KEY")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if openai_key:
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "openai>=1.12.0 is required. Install with: pip install -e ."
            ) from e

        client = OpenAI(api_key=openai_key)
        return ("openai", client, openai_model)

    raise RuntimeError(
        "No Azure OpenAI or OpenAI credentials found. Set env vars per .env.example."
    )


def build_prompt(task: Dict[str, Any]) -> str:
    return (
        f"File: {task['file']}\n"
        f"Function: {task['function']}\n"
        f"Signature: {task['signature']}\n"
        "\nRequirements:\n"
        f"{task['description']}\n"
        "\nOutput only valid Python code for this file, nothing else.\n"
    )


def save_code(out_dir: Path, file: str, code: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / file).write_text(code, encoding="utf-8")


def chat_complete(
    vendor: str,
    client,
    model_or_deploy: str,
    prompt: str,
    responses_model: str | None = None,
) -> str:
    if vendor == "azure":
        resp = client.chat.completions.create(
            model=model_or_deploy,
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""

    # OpenAI path
    model = model_or_deploy

    # If a specific Responses API model is requested, honor it (no fallback)
    if responses_model:
        try:
            resp = client.responses.create(
                model=responses_model,
                input=f"{SYSTEM_INSTRUCTIONS}\n\n{prompt}",
            )
        except Exception as e:
            raise RuntimeError(
                f"Responses API call failed for explicit model {responses_model}: {e}"
            )

        text = getattr(resp, "output_text", None)
        if isinstance(text, str) and text.strip():
            return text
        try:
            parts = []
            for out in getattr(resp, "output", []) or []:
                for c in getattr(out, "content", []) or []:
                    if getattr(c, "type", None) in ("output_text", "text"):
                        t = getattr(c, "text", None)
                        if isinstance(t, str):
                            parts.append(t)
            if parts:
                return "".join(parts)
        except Exception:
            pass
        return ""

    # Prefer Responses API automatically for o* models (e.g., o4) when not explicitly set
    if model.lower().startswith("o"):
        def try_responses(m: str):
            return client.responses.create(
                model=m,
                input=f"{SYSTEM_INSTRUCTIONS}\n\n{prompt}",
            )

        resp = None
        try:
            resp = try_responses(model)
        except Exception as e:
            msg = str(e).lower()
            if "model_not_found" in msg or "does not exist" in msg:
                for cand in ("o4-mini", "o3-mini"):
                    try:
                        print(f"[yellow]Model {model} unavailable; trying {cand} via Responses API[/yellow]")
                        resp = try_responses(cand)
                        break
                    except Exception:
                        continue
            if resp is None:
                print(f"[yellow]Responses API unavailable for {model}; falling back to gpt-4o chat.completions[/yellow]")
                # Fall back to chat.completions with gpt-4o
                cc = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                )
                return cc.choices[0].message.content or ""

        # SDK often exposes a convenience property
        text = getattr(resp, "output_text", None)
        if isinstance(text, str) and text.strip():
            return text

        # Fallback attempt: concatenate text segments if present
        try:
            parts = []
            for out in getattr(resp, "output", []) or []:
                for c in getattr(out, "content", []) or []:
                    if getattr(c, "type", None) in ("output_text", "text"):
                        t = getattr(c, "text", None)
                        if isinstance(t, str):
                            parts.append(t)
            if parts:
                return "".join(parts)
        except Exception:
            pass

        # Last resort
        return ""

    # Default to Chat Completions for non-o* models
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""


def run_pytest_for(src: Path) -> int:
    # Delegate to the tools runner to keep behavior consistent
    import subprocess, sys

    env = os.environ.copy()
    env["SRC_PATH"] = str(src)
    cmd = [sys.executable, "tools/run_tests.py", "--src", str(src)]
    return subprocess.call(cmd, env=env)


def main():
    ap = argparse.ArgumentParser(description="Generate task solutions with Azure/OpenAI and test them")
    ap.add_argument("--tasks", default="prompts/tasks.yaml")
    ap.add_argument("--out", default="variants/azure/src")
    ap.add_argument("--run-tests", action="store_true")
    ap.add_argument(
        "--responses-model",
        default=None,
        help="Force OpenAI Responses API with this model (e.g., o4, o4-mini). Overrides automatic detection.",
    )
    args = ap.parse_args()

    vendor, client, model = ensure_client()
    data = load_tasks(args.tasks)

    # Allow env var override if CLI not provided
    responses_model = args.responses_model or os.getenv("OPENAI_RESPONSES_MODEL")

    out_dir = Path(args.out)
    latencies = {}
    for task in data.get("tasks", []):
        prompt = build_prompt(task)
        t0 = time.perf_counter()
        code = chat_complete(vendor, client, model, prompt, responses_model=responses_model)
        dt = time.perf_counter() - t0
        latencies[task["id"]] = dt
        save_code(out_dir, task["file"], code)
        print(f"[green]Generated[/green] {task['file']} in {dt:.2f}s")

    # Write a small report
    report_path = out_dir.parent / "report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"vendor={vendor}, model/deployment={model}\n")
        for k, v in latencies.items():
            f.write(f"{k}: {v:.3f}s\n")
    print(f"Latency report -> {report_path}")

    if args.run_tests:
        rc = run_pytest_for(out_dir)
        print(f"pytest exit code: {rc}")


if __name__ == "__main__":
    main()
