"""Centralized LLM / AI provider configuration.

Single source of truth for API keys, base URLs, and OpenAI-compatible client
instances.  Every module that needs an API key or client should import from
here instead of reading ``os.getenv("OPENAI_API_KEY")`` directly.

Supports provider swapping via environment variables:
    OPENAI_API_KEY      – API key (required for real inference)
    OPENAI_BASE_URL     – Base URL override (for DeepSeek, Azure, local, etc.)

The module deliberately uses the OpenAI SDK's ``api_key`` / ``base_url``
constructor args so that non-OpenAI providers with compatible APIs (DeepSeek,
Together, Groq, local llama.cpp, Azure via proxy) work transparently.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_BASE_URL = "https://api.openai.com/v1"

# ---------------------------------------------------------------------------
# Internal state — singleton client, thread-safe
# ---------------------------------------------------------------------------
_client: Any | None = None
_client_lock = threading.Lock()
_logged_provider = False


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_api_key() -> str:
    """Return the configured API key, or empty string if unset."""
    return os.getenv("OPENAI_API_KEY", "").strip()


def get_base_url() -> str:
    """Return the configured base URL, respecting OPENAI_BASE_URL."""
    return os.getenv("OPENAI_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


def is_available() -> bool:
    """Return True if an API key is configured (non-empty)."""
    return bool(get_api_key())


def provider_label() -> str:
    """Return a human-readable label for the active provider.

    Uses the base URL to infer the provider name.  Useful for logging and
    health endpoints.
    """
    base = get_base_url()
    if "api.openai.com" in base:
        return "openai"
    if "api.deepseek.com" in base:
        return "deepseek"
    if "openai.azure.com" in base:
        return "azure-openai"
    if "api.anthropic.com" in base:
        return "anthropic"
    if "api.together.xyz" in base or "together.ai" in base:
        return "together"
    if "api.groq.com" in base:
        return "groq"
    if "127.0.0.1" in base or "localhost" in base:
        return "local"
    return "custom"


def validate_key_format(key: str | None = None) -> tuple[bool, str]:
    """Light format check on the API key.  Does NOT call any remote API.

    Returns ``(ok, message)`` — ``ok`` is True when the key looks plausible.
    """
    k = (key or get_api_key()).strip()
    if not k:
        return False, "No API key set (OPENAI_API_KEY is empty)"

    base = get_base_url()

    # Local servers don't need a real key
    if "127.0.0.1" in base or "localhost" in base:
        return True, f"Local provider — key accepted as-is ({provider_label()})"

    if k.startswith("sk-ant-"):
        return True, "Anthropic key detected"
    if k.startswith("sk-"):
        return True, "OpenAI-format key detected"
    if len(k) > 20:
        return True, f"Non-standard key format for {provider_label()} — accepted (length {len(k)})"

    return False, f"Key looks too short or malformed ({len(k)} chars)"


def get_openai_client(*, force_new: bool = False) -> Any:
    """Return a thread-safe singleton ``openai.OpenAI`` client.

    The client is constructed with explicit ``api_key`` and ``base_url`` so
    that provider swapping works even when the SDK's auto-detection would
    pick up stale values.

    Pass ``force_new=True`` to discard the cached client (e.g. after key
    rotation).
    """
    global _client, _logged_provider

    if _client is not None and not force_new:
        return _client

    with _client_lock:
        if _client is not None and not force_new:
            return _client

        from openai import OpenAI

        api_key = get_api_key()
        base_url = get_base_url()

        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url != _DEFAULT_BASE_URL:
            kwargs["base_url"] = base_url

        _client = OpenAI(**kwargs)

        if not _logged_provider:
            _logged_provider = True
            label = provider_label()
            ok, msg = validate_key_format(api_key)
            if ok:
                logger.info("LLM provider: %s (%s)", label, msg)
            else:
                logger.warning("LLM provider: %s — %s", label, msg)

        return _client


def reset_client() -> None:
    """Discard the cached client.  Next call to ``get_openai_client()``
    will re-read env vars and construct a fresh client.  Useful after
    key rotation or profile switch.
    """
    global _client, _logged_provider
    with _client_lock:
        _client = None
        _logged_provider = False


def build_auth_headers() -> dict[str, str]:
    """Return Authorization + Content-Type headers for direct httpx calls.

    This is for code paths that bypass the OpenAI SDK (e.g. streaming TTS
    via raw httpx).  Always use this instead of hand-rolling Bearer headers.
    """
    return {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json",
    }


def build_api_url(path: str) -> str:
    """Build a full API URL from the configured base URL and a path.

    Example::

        build_api_url("/audio/speech")
        # → "https://api.openai.com/v1/audio/speech"  (default)
        # → "https://api.deepseek.com/v1/audio/speech" (if OPENAI_BASE_URL set)
    """
    base = get_base_url()
    # Ensure path starts with /
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"
