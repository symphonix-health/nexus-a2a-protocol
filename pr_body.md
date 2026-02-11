## Stabilize diagnosis agent (non-blocking LLM) + live Command Centre monitoring

### Summary

- Diagnosis agent: Added `tasks/sendSubscribe`, split core logic to `_do_assess()`, wrapped `llm_chat` with `asyncio.to_thread` to avoid blocking the event loop, and cleaned task metrics/event publishing.
- Telemed Scribe Summariser + Consent Analyser: Wrapped `llm_chat` with `asyncio.to_thread` to prevent stalls when `OPENAI_API_KEY` is set.
- Command Centre: Verified Redis pub/sub and static path; dashboard reflects live metrics and agent health.
- Tools: Fixed `tools/continuous_traffic.py` (import `os`) for sustained load; added helpers `tools/test_diagnosis_stability.py` and `tools/_check_health.py`.

### Verification

- Stress: 10/10 diagnosis tasks accepted and completed; 0 errors; agent remained responsive under real OpenAI calls.
- Scenarios: All 10 journeys (5 base + 5 additional) executed end-to-end.
- Command Centre: Healthy; metrics increase under continuous traffic; live events emitted via Redis.

### Affected (high level)

- `demos/ed-triage/diagnosis-agent/app/main.py`
- `demos/telemed-scribe/summariser-agent/app/main.py`
- `demos/consent-verification/consent-analyser/app/main.py`
- `shared/command-centre/app/main.py`
- `tools/continuous_traffic.py`, `tools/test_diagnosis_stability.py`, `tools/_check_health.py`

### Notes

- Non-blocking LLM preserves responsiveness even with longer upstream latency.
- Status may temporarily read "degraded" under heavy LLM load due to average latency; functionality remains stable.
