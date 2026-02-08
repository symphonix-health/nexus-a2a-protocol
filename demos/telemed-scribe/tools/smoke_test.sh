#!/usr/bin/env bash
set -euo pipefail
RPC="${RPC:-http://localhost:8031/rpc}"
EVENTS="${EVENTS:-http://localhost:8031/events}"
EHR="${EHR:-http://localhost:8033/rpc}"
TOKEN="${NEXUS_JWT_TOKEN:?Set NEXUS_JWT_TOKEN in .env}"

echo "=== Telemed Scribe Smoke Test ==="
REQ='{"jsonrpc":"2.0","id":"req-2001","method":"tasks/sendSubscribe","params":{"task":{"patient_ref":"Patient/456","inputs":{"transcript":"DOCTOR: What brings you in?\nPATIENT: Fever and headache.\nDOCTOR: Plan: symptomatic and review."}}}}'
RESP=$(curl -fsS -X POST "$RPC" -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d "$REQ")
echo "RPC Response: $RESP"
TASK_ID=$(echo "$RESP" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['result']['task_id'])")
echo "Task ID: $TASK_ID"
echo "--- SSE Stream ---"
timeout 10 curl -N -H "Authorization: Bearer $TOKEN" "${EVENTS}/${TASK_ID}" || true
echo ""

echo "--- Latest EHR Note ---"
GET='{"jsonrpc":"2.0","id":"req-2002","method":"ehr/getLatestNote","params":{"patient_ref":"Patient/456"}}'
curl -fsS -X POST "$EHR" -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d "$GET"
echo ""
echo "=== Smoke Test Complete ==="
