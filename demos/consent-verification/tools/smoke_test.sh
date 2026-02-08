#!/usr/bin/env bash
set -euo pipefail
RPC="${RPC:-http://localhost:8041/rpc}"
EVENTS="${EVENTS:-http://localhost:8041/events}"
HITL="${HITL:-http://localhost:8044/rpc}"
TOKEN="${NEXUS_JWT_TOKEN:?Set NEXUS_JWT_TOKEN in .env}"

echo "=== Consent Verification Smoke Test ==="
REQ='{"jsonrpc":"2.0","id":"req-3001","method":"tasks/sendSubscribe","params":{"task":{"patient_ref":"Patient/789","inputs":{"data_type":"DischargeSummary","purpose":"claims_processing","consent_text":"I authorise Provider Hospital to share discharge summaries with MyInsurance Ltd for claims processing for 2025."}}}}'
RESP=$(curl -fsS -X POST "$RPC" -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d "$REQ")
echo "RPC Response: $RESP"
TASK_ID=$(echo "$RESP" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['result']['task_id'])")
echo "Task ID: $TASK_ID"
echo "--- SSE Stream ---"
timeout 10 curl -N -H "Authorization: Bearer $TOKEN" "${EVENTS}/${TASK_ID}" || true
echo ""
echo "=== Smoke Test Complete ==="
