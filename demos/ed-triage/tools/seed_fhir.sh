#!/usr/bin/env bash
set -euo pipefail
FHIR_BASE="${FHIR_BASE:-http://localhost:8080/fhir}"

curl -sS -X PUT "${FHIR_BASE}/Patient/123" -H "Content-Type: application/fhir+json" -d '{
  "resourceType":"Patient","id":"123",
  "name":[{"family":"Doe","given":["Jane"]}],
  "gender":"female","birthDate":"1972-04-10"
}' >/dev/null

curl -sS -X POST "${FHIR_BASE}/AllergyIntolerance" -H "Content-Type: application/fhir+json" -d '{
  "resourceType":"AllergyIntolerance",
  "clinicalStatus":{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical","code":"active"}]},
  "verificationStatus":{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/allergyintolerance-verification","code":"confirmed"}]},
  "patient":{"reference":"Patient/123"},
  "code":{"text":"Penicillin"}
}' >/dev/null

echo "FHIR seed complete."
