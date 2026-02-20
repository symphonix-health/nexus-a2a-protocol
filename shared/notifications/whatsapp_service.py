"""WhatsApp notification service via Twilio API.

Falls back to a no-op stub when Twilio credentials are missing.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

_TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
_TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
_TWILIO_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")


def _has_credentials() -> bool:
    return bool(_TWILIO_SID and _TWILIO_TOKEN)


def send_whatsapp(
    to: str,
    body: str,
    *,
    media_url: str | None = None,
) -> dict[str, Any]:
    """Send a WhatsApp message via Twilio REST API.

    ``to`` must include the ``whatsapp:`` prefix, e.g. ``whatsapp:+15551234567``.

    Returns a dict with ``ok``, ``sid``, and ``stub`` flag.
    """
    if not to.startswith("whatsapp:"):
        to = f"whatsapp:{to}"

    if not _has_credentials():
        return {
            "ok": True,
            "stub": True,
            "detail": "Twilio credentials not configured – WhatsApp simulated",
            "to": to,
            "body_preview": body[:80],
        }

    url = f"https://api.twilio.com/2010-04-01/Accounts/{_TWILIO_SID}/Messages.json"
    data: dict[str, str] = {
        "From": _TWILIO_FROM,
        "To": to,
        "Body": body,
    }
    if media_url:
        data["MediaUrl"] = media_url

    try:
        resp = httpx.post(
            url,
            data=data,
            auth=(_TWILIO_SID, _TWILIO_TOKEN),
            timeout=15.0,
        )
        result = resp.json()
        if resp.status_code < 300:
            return {
                "ok": True,
                "stub": False,
                "sid": result.get("sid"),
                "to": to,
            }
        return {
            "ok": False,
            "stub": False,
            "error": result.get("message", resp.text),
            "to": to,
        }
    except Exception as exc:
        return {
            "ok": False,
            "stub": False,
            "error": str(exc),
            "to": to,
        }
