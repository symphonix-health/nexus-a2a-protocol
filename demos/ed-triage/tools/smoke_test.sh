#!/usr/bin/env bash
set -euo pipefail
TRIAGE_RPC="${TRIAGE_RPC:-http://localhost:8021/rpc}"
TRIAGE_EVENTS="${TRIAGE_EVENTS:-http://localhost:8021/events}"
TOKEN="${NEXUS_JWT_TOKEN:?Set NEXUS_JWT_TOKEN in .env}"

echo "=== ED Triage Smoke Test ==="
REQ='{"jsonrpc":"2.0","id":"req-1001","method":"tasks/sendSubscribe","params":{"conversation_id":"conv-ed-001","task":{"type":"ClinicalRiskAssessment","patient_ref":"Patient/123","inputs":{"chief_complaint":"Chest pain and shortness of breath","onset":"2 hours","age":54}}}}'
RESP=$(curl -fsS -X POST "$TRIAGE_RPC" -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d "$REQ")
echo "RPC Response: $RESP"
TASK_ID=$(echo "$RESP" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['result']['task_id'])")
echo "Task ID: $TASK_ID"
echo "--- SSE Stream ---"
timeout 10 curl -N -H "Authorization: Bearer $TOKEN" "${TRIAGE_EVENTS}/${TASK_ID}" || true
echo ""
echo "=== Smoke Test Complete ==="
