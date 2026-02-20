from __future__ import annotations


def select_framework(chief_complaint: str, urgency: str) -> str:
    complaint = (chief_complaint or "").lower()
    urg = (urgency or "").lower()

    if urg in {"critical", "emergency"}:
        return "abcde"
    if "pain" in complaint or "chest" in complaint:
        return "socrates"
    return "calgary_cambridge"
