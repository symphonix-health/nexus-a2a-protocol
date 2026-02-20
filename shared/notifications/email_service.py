"""SMTP e-mail notification service.

Supports real delivery via Gmail app-password flow or any STARTTLS-capable
SMTP relay.  Falls back to a no-op stub when credentials are missing so that
scenario runs never crash on notification steps.
"""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

_SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
_SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
_SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
_SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
_SMTP_FROM = os.getenv("SMTP_FROM", "")


def _has_credentials() -> bool:
    return bool(_SMTP_USERNAME and _SMTP_PASSWORD)


def send_email(
    to: str | list[str],
    subject: str,
    body_html: str,
    *,
    body_text: str | None = None,
    cc: str | list[str] | None = None,
    reply_to: str | None = None,
) -> dict[str, Any]:
    """Send an e-mail via SMTP.

    Returns a dict with ``ok``, ``message_id``, and ``stub`` flag.
    """
    recipients = [to] if isinstance(to, str) else list(to)
    cc_list = [cc] if isinstance(cc, str) else list(cc or [])

    if not _has_credentials():
        return {
            "ok": True,
            "stub": True,
            "detail": "SMTP credentials not configured – email simulated",
            "to": recipients,
            "subject": subject,
        }

    msg = MIMEMultipart("alternative")
    msg["From"] = _SMTP_FROM or _SMTP_USERNAME
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    if reply_to:
        msg["Reply-To"] = reply_to

    if body_text:
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    all_recipients = recipients + cc_list

    try:
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(_SMTP_USERNAME, _SMTP_PASSWORD)
            server.sendmail(msg["From"], all_recipients, msg.as_string())
        return {
            "ok": True,
            "stub": False,
            "to": recipients,
            "subject": subject,
        }
    except Exception as exc:
        return {
            "ok": False,
            "stub": False,
            "error": str(exc),
            "to": recipients,
            "subject": subject,
        }
