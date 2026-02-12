## Make triage-agent health thresholds configurable for LLM latency

### Summary

- Introduces environment-configurable health thresholds used by `HealthMonitor`:
  - `NEXUS_HEALTH_ERROR_UNHEALTHY` (default `0.10`)
  - `NEXUS_HEALTH_ERROR_DEGRADED` (default `0.05`)
  - `NEXUS_HEALTH_LATENCY_DEGRADED_MS` (default `5000`)
- Keeps existing defaults unchanged; enables triage- and LLM-heavy agents to relax latency threshold (e.g., `60000`) without code changes.

### Rationale

- Under real OpenAI calls, average task latency can exceed 50s. Previous fixed 5s threshold marked agents as `degraded`/`unhealthy`, even when error rate was 0.
- Configurable thresholds avoid false signals while preserving safety via error-rate gates.

### Usage (example for triage-agent)

```powershell
$env:NEXUS_HEALTH_LATENCY_DEGRADED_MS="60000"
```

### Affected files

- `shared/nexus_common/health.py`
