"""Agent certificate registry for mTLS thumbprint-to-agent mapping."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "agent_cert_registry.json"
)

_HEX_ONLY_RE = re.compile(r"^[0-9a-fA-F]+$")
_XFCC_HASH_RE = re.compile(r"(?:^|;)\s*Hash=([^;]+)")


def normalize_thumbprint(value: str | None) -> str:
    """Normalize thumbprints for deterministic comparisons.

    Hex thumbprints are normalized by stripping separators and lowercasing.
    Non-hex values are returned trimmed so token-bound thumbprints still match
    when providers use base64url form.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    collapsed = raw.replace(":", "").replace("-", "").replace(" ", "")
    if _HEX_ONLY_RE.match(collapsed):
        return collapsed.lower()
    return raw


def extract_thumbprint_from_xfcc(xfcc: str | None) -> str | None:
    """Extract a cert hash from x-forwarded-client-cert when present."""
    raw = str(xfcc or "").strip()
    if not raw:
        return None
    match = _XFCC_HASH_RE.search(raw)
    if not match:
        return None
    return normalize_thumbprint(match.group(1))


@dataclass(frozen=True)
class AgentCertRegistry:
    """Immutable thumbprint->agent principal lookup."""

    thumbprint_to_agent: dict[str, str]

    def resolve_agent_principal(self, thumbprint: str | None) -> str | None:
        key = normalize_thumbprint(thumbprint)
        if not key:
            return None
        return self.thumbprint_to_agent.get(key)

    @property
    def is_empty(self) -> bool:
        return not self.thumbprint_to_agent


def _path_from_env() -> Path:
    raw = os.getenv("NEXUS_AGENT_CERT_REGISTRY_PATH", "").strip()
    return Path(raw) if raw else _DEFAULT_REGISTRY_PATH


def _parse_registry(data: dict[str, Any]) -> AgentCertRegistry:
    mapping: dict[str, str] = {}

    # Preferred shape:
    # { "thumbprints": { "<thumbprint>": "agent_principal" } }
    thumbprints = data.get("thumbprints")
    if isinstance(thumbprints, dict):
        for raw_thumb, raw_agent in thumbprints.items():
            thumb = normalize_thumbprint(str(raw_thumb))
            agent = str(raw_agent or "").strip()
            if thumb and agent:
                mapping[thumb] = agent

    # Alternate shape:
    # { "agents": { "triage_agent": { "thumbprints": ["..."] } } }
    agents = data.get("agents")
    if isinstance(agents, dict):
        for raw_agent, cfg in agents.items():
            if not isinstance(cfg, dict):
                continue
            agent = str(raw_agent).strip()
            if not agent:
                continue
            listed = cfg.get("thumbprints") or cfg.get("cert_thumbprints") or []
            if isinstance(listed, list):
                for item in listed:
                    thumb = normalize_thumbprint(str(item))
                    if thumb:
                        mapping[thumb] = agent

    return AgentCertRegistry(thumbprint_to_agent=mapping)


@lru_cache(maxsize=16)
def _load_registry_for_path(path_str: str) -> AgentCertRegistry:
    path = Path(path_str)
    if not path.is_file():
        return AgentCertRegistry(thumbprint_to_agent={})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return AgentCertRegistry(thumbprint_to_agent={})
    if not isinstance(data, dict):
        return AgentCertRegistry(thumbprint_to_agent={})
    return _parse_registry(data)


def get_agent_cert_registry() -> AgentCertRegistry:
    path = _path_from_env().resolve()
    return _load_registry_for_path(str(path))


def reload_agent_cert_registry() -> AgentCertRegistry:
    """Clear cache and reload registry (used by tests)."""
    _load_registry_for_path.cache_clear()
    return get_agent_cert_registry()
