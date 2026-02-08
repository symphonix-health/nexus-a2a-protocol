#!/usr/bin/env bash
set -euo pipefail
RPC="${RPC:-http://localhost:8053/rpc}"
EVENTS="${EVENTS:-http://localhost:8053/events}"
TOKEN="${NEXUS_JWT_TOKEN:?Set NEXUS_JWT_TOKEN in .env}"

echo "=== Public Health Surveillance Smoke Test ==="
REQ='{"jsonrpc":"2.0","id":"req-4001","method":"tasks/sendSubscribe","params":{"task":{"pathogen":"cholera","region":"Gauteng"}}}'
RESP=$(curl -fsS -X POST "$RPC" -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d "$REQ")
echo "RPC Response: $RESP"
TASK_ID=$(echo "$RESP" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['result']['task_id'])")
echo "Task ID: $TASK_ID"
echo "--- SSE Stream ---"
timeout 10 curl -N -H "Authorization: Bearer $TOKEN" "${EVENTS}/${TASK_ID}" || true
echo ""
echo "=== Smoke Test Complete ==="
