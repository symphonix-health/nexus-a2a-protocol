# Memory Soak Report

- Run started: `2026-02-27T19:51:43.813828+00:00`
- Duration: `30 minutes`
- Sample interval: `10.0s`
- Target RPC: `http://localhost:8100/rpc/triage`

## Traffic

- Requests sent: `655`
- Responses OK: `653`
- HTTP errors: `0`
- Transport errors: `2`
- Success rate: `99.69%`

## Service RSS Summary

| Service | Samples | Start MiB | End MiB | Delta MiB | Max MiB | P95 MiB |
|---|---:|---:|---:|---:|---:|---:|
| diagnosis_agent | 123 | 24.58 | 66.30 | 41.72 | 103.57 | 100.92 |
| command_centre | 123 | 14.14 | 43.56 | 29.42 | 43.95 | 43.79 |
| openhie_mediator | 123 | 16.66 | 28.15 | 11.50 | 54.96 | 50.36 |
| triage_agent | 123 | 17.70 | 22.96 | 5.26 | 49.02 | 48.51 |
| on_demand_gateway | 123 | 21.99 | 25.65 | 3.66 | 26.14 | 25.93 |
| pharmacy_agent | 123 | 8.78 | 10.98 | 2.20 | 11.89 | 11.68 |
| discharge_agent | 123 | 8.78 | 10.96 | 2.18 | 11.63 | 11.07 |
| clinician_avatar_agent | 123 | 8.77 | 10.86 | 2.09 | 11.66 | 11.20 |
| bed_manager_agent | 123 | 8.74 | 10.66 | 1.92 | 11.39 | 10.93 |
| care_coordinator | 123 | 8.73 | 10.61 | 1.88 | 11.90 | 11.20 |
| central_surveillance | 123 | 8.89 | 10.70 | 1.81 | 13.05 | 11.49 |
| telehealth_agent | 123 | 8.93 | 10.60 | 1.67 | 11.79 | 11.28 |
| hitl_ui | 123 | 8.79 | 10.41 | 1.62 | 11.70 | 11.35 |
| specialty_care_agent | 123 | 8.95 | 10.55 | 1.60 | 11.59 | 11.09 |
| osint_agent | 123 | 9.16 | 10.73 | 1.57 | 11.66 | 11.45 |
| transcriber_agent | 123 | 8.96 | 10.52 | 1.55 | 11.46 | 11.06 |
| consent_analyser | 123 | 8.65 | 10.20 | 1.54 | 11.58 | 11.30 |
| primary_care_agent | 123 | 8.75 | 10.22 | 1.47 | 11.36 | 11.02 |
| followup_scheduler | 123 | 8.91 | 10.28 | 1.37 | 11.39 | 10.96 |
| ehr_writer_agent | 123 | 8.89 | 10.25 | 1.35 | 11.73 | 11.27 |
| hospital_reporter | 123 | 9.59 | 10.91 | 1.32 | 12.21 | 11.66 |
| ccm_agent | 123 | 8.80 | 10.11 | 1.32 | 11.73 | 11.16 |
| home_visit_agent | 123 | 8.80 | 10.10 | 1.29 | 11.65 | 11.09 |
| provider_agent | 123 | 8.80 | 9.90 | 1.10 | 11.49 | 11.02 |
| insurer_agent | 123 | 9.46 | 10.45 | 1.00 | 11.88 | 11.50 |
| summariser_agent | 123 | 8.89 | 9.79 | 0.89 | 11.35 | 11.04 |
| imaging_agent | 123 | 13.21 | 10.45 | -2.76 | 14.09 | 11.41 |

## Artifacts

- Raw service RSS time series: `soak_output\soak_20260227T202144Z\rss_timeseries.csv`
- Raw per-PID RSS time series: `soak_output\soak_20260227T202144Z\rss_by_pid_timeseries.csv`
- JSON summary: `soak_output\soak_20260227T202144Z\summary.json`
