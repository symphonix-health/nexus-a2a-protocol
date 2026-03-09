"""Agent registry and URL resolution helpers shared by SDK transports."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_RELATIVE = Path("config") / "agents.json"


@dataclass(slots=True)
class AgentInfo:
    """Metadata for a single Nexus agent resolved from env/config."""

    alias: str
    port: int
    url: str
    description: str = ""
    category: str = ""
    path: str = ""
    rpc_env: str = ""
    env: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, "")}



def _find_config_path(config_path: str | None = None) -> Path | None:
    if config_path:
        explicit = Path(config_path)
        return explicit if explicit.is_file() else None

    anchor = Path(__file__).resolve()
    for parent in (anchor.parent, *anchor.parents):
        candidate = parent / _DEFAULT_CONFIG_RELATIVE
        if candidate.is_file():
            return candidate
    return None



def load_agent_registry(config_path: str | None = None) -> dict[str, AgentInfo]:
    """Load alias->AgentInfo registry from AGENT_URLS or config/agents.json."""
    env_urls = os.getenv("AGENT_URLS", "").strip()
    if env_urls:
        registry: dict[str, AgentInfo] = {}
        for raw in env_urls.split(","):
            url = raw.strip().rstrip("/")
            if not url:
                continue
            try:
                port = int(url.rsplit(":", 1)[-1])
            except (ValueError, IndexError):
                port = 0
            alias = f"agent_{port}" if port else url
            registry[alias] = AgentInfo(alias=alias, port=port, url=url)
        if registry:
            logger.info("Loaded %d agents from AGENT_URLS", len(registry))
            return registry

    cfg_path = _find_config_path(config_path)
    if cfg_path is None:
        logger.warning("No agent config found (AGENT_URLS unset, agents.json not found)")
        return {}

    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read %s: %s", cfg_path, exc)
        return {}

    grouped = raw.get("agents", {})
    if not isinstance(grouped, dict):
        return {}

    registry: dict[str, AgentInfo] = {}
    for category, group in grouped.items():
        if not isinstance(group, dict):
            continue
        for alias, info in group.items():
            if not isinstance(info, dict):
                continue
            port = info.get("port")
            if not isinstance(port, int) or port <= 0:
                continue
            registry[alias] = AgentInfo(
                alias=alias,
                port=port,
                url=f"http://localhost:{port}",
                description=str(info.get("description", "")),
                category=str(category),
                path=str(info.get("path", "")),
                rpc_env=str(info.get("rpc_env", "")),
                env=str(info.get("env", "")),
            )

    logger.info("Loaded %d agents from %s", len(registry), cfg_path)
    return registry



def resolve_agent_url(alias_or_url: str, registry: dict[str, AgentInfo]) -> str:
    """Resolve alias to base URL, or pass through raw HTTP(S) URL."""
    candidate = str(alias_or_url).strip()
    if candidate.startswith("http://") or candidate.startswith("https://"):
        return candidate.rstrip("/")

    info = registry.get(candidate)
    if info is None:
        available = ", ".join(sorted(registry.keys())) if registry else "(none)"
        raise ValueError(f"Unknown agent alias {candidate!r}. Available: {available}")
    return info.url.rstrip("/")
