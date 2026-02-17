"""Deterministic LLM helper — uses OpenAI when API key is set, otherwise mock output."""

from __future__ import annotations

import os


def llm_available() -> bool:
    """Check whether an OpenAI API key is configured."""
    return bool(os.getenv("OPENAI_API_KEY"))


def llm_chat(system: str, user: str) -> str:
    """Call OpenAI chat completion, or return deterministic mock when key is absent."""
    if llm_available():
        try:
            from openai import OpenAI

            client = OpenAI()
            kwargs = {}
            # If the system prompt asks for JSON, enforce it via the API
            if "json" in system.lower():
                kwargs["response_format"] = {"type": "json_object"}

            resp = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                **kwargs,
            )
            content = resp.choices[0].message.content or ""

            # Additional safety: strip known markdown markers
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]

            return content.strip()
        except Exception:
            pass  # Fallback to mock if client init or API call fails

    # ── Deterministic Mocks ─────────────────────────────────────────
    sys_lower = system.lower()

    # 1. ED Triage: Diagnosis Agent
    if "diagnose" in sys_lower or "clinical assessment" in sys_lower:
        return (
            '{"diagnosis": "Viral Upper Respiratory Infection", '
            '"confidence": 0.92, '
            '"reasoning": "Symptoms of cough and sore throat without fever suggest viral etiology.", '
            '"recommended_specialty": "General Practice", '
            '"urgency": "low"}'
        )

    # 2. Telemed Scribe: Transcriber Agent
    if "transcriber" in sys_lower or "transcribe" in sys_lower:
        return '{"transcript": "Patient complains of headache and nausea starting yesterday. No history of migraines."}'

    # 3. Telemed Scribe: Summariser Agent
    if "summarize" in sys_lower or "medical summary" in sys_lower:
        return (
            '{"summary": "Acute onset headache and nausea.", '
            '"key_symptoms": ["headache", "nausea"], '
            '"medications": [], '
            '"allergies": []}'
        )

    # 4. Telemed Scribe: EHR Writer Agent
    # Returns a minimal FHIR Bundle to satisfy the agent's validation
    if "ehr" in sys_lower or "fhir" in sys_lower:
        return (
            '{"resourceType": "Bundle", "type": "transaction", "entry": [{'
            '  "resource": {"resourceType": "Encounter", "status": "finished", "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"}},'
            '  "request": {"method": "POST", "url": "Encounter"}'
            "}]}"
        )

    # 5. Consent Verification: Consent Analyser
    if "consent" in sys_lower or "policy" in sys_lower:
        # Check user prompt for "deny" hints, otherwise permit
        if "deny" in user.lower() or "revoked" in user.lower():
            return '{"allowed": false, "reason": "Consent revoked by patient.", "obligations": []}'
        return (
            '{"allowed": true, "reason": "Valid active consent found.", "obligations": ["logging"]}'
        )

    # 6. Public Health: OSINT Agent
    if "osint" in sys_lower or "alert" in sys_lower:
        return (
            '{"risk_score": 0.75, '
            '"relevant_articles": [{"title": "Flu surge in region", "url": "http://news.local/flu", "relevance": 0.8}], '
            '"summary": "Moderate risk of local outbreak detected."}'
        )

    # Default fallback
    return f'{{"mock_response": "unhandled_system_prompt", "preview": "{system[:20]}..."}}'
