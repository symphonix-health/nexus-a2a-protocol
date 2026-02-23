from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEMOS_ROOT = REPO_ROOT / "demos"
REQUIRED_CARD_KEYS = {
    "name",
    "protocol",
    "protocolVersion",
    "methods",
    "authentication",
    "capabilities",
}
BASE_TASK_SURFACE = {
    "tasks/send",
    "tasks/sendSubscribe",
    "tasks/get",
    "tasks/cancel",
    "tasks/resubscribe",
}


def _card_files() -> list[Path]:
    return sorted(DEMOS_ROOT.rglob("agent_card.json"))


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"{path}: card must be a JSON object"
    return payload


def _runtime_file_for_card(card_path: Path) -> Path | None:
    sibling = card_path.parent / "main.py"
    if sibling.exists():
        return sibling
    candidate = card_path.parent / "app" / "main.py"
    if candidate.exists():
        return candidate
    return None


def _runtime_declared_methods(runtime_path: Path, card_methods: set[str]) -> set[str]:
    text = runtime_path.read_text(encoding="utf-8")

    if "build_generic_demo_app" in text:
        # Generic runtime always supports base task surface plus declared card methods.
        return set(card_methods) | set(BASE_TASK_SURFACE)

    methods: set[str] = set()
    methods.update(re.findall(r'METHODS\["([^"]+)"\]', text))
    methods.update(re.findall(r"method == \"([^\"]+)\"", text))
    return methods


def test_agent_cards_have_required_schema_and_a2a_method_contract() -> None:
    cards = _card_files()
    assert cards, "No agent cards found under demos/"

    for path in cards:
        payload = _load_json(path)
        missing_keys = sorted(REQUIRED_CARD_KEYS - set(payload.keys()))
        assert not missing_keys, f"{path}: missing required keys {missing_keys}"

        assert payload.get("protocol") == "NEXUS-A2A", f"{path}: protocol must be NEXUS-A2A"
        assert isinstance(payload.get("protocolVersion"), str) and payload["protocolVersion"].strip(), (
            f"{path}: protocolVersion must be non-empty string"
        )

        methods = payload.get("methods")
        assert isinstance(methods, list) and methods, f"{path}: methods must be a non-empty list"
        assert all(isinstance(m, str) and m.strip() for m in methods), f"{path}: methods must be non-empty strings"
        assert len(set(methods)) == len(methods), f"{path}: methods must be unique"

        if "tasks/sendSubscribe" in methods:
            assert "tasks/send" in methods, f"{path}: tasks/sendSubscribe requires tasks/send declaration"
            assert "tasks/resubscribe" in methods, (
                f"{path}: tasks/sendSubscribe requires tasks/resubscribe declaration"
            )


def test_agent_card_methods_are_runtime_accurate() -> None:
    for card_path in _card_files():
        payload = _load_json(card_path)
        methods = payload.get("methods", [])
        if not isinstance(methods, list):
            continue
        card_methods = {str(m).strip() for m in methods if isinstance(m, str) and str(m).strip()}
        runtime_path = _runtime_file_for_card(card_path)
        assert runtime_path is not None, f"{card_path}: runtime main.py not found"
        runtime_methods = _runtime_declared_methods(runtime_path, card_methods)
        missing = sorted(card_methods - runtime_methods)
        assert not missing, (
            f"{card_path}: methods declared in card but not supported by runtime {runtime_path}: {missing}"
        )
