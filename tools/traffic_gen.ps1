# PowerShell Traffic Generator for Command Centre
# Sends continuous triage tasks to generate real metrics

$ErrorActionPreference = "SilentlyContinue"

# Configuration
$TRIAGE_URL = "http://localhost:8021/rpc"
$COMPLAINTS = @(
    "chest pain", "shortness of breath", "abdominal pain", "severe headache",
    "dizziness", "fever", "nausea", "back pain", "leg pain",
    "difficulty breathing", "rapid heartbeat", "weakness", "confusion"
)

# Generate JWT token
$env:PYTHONPATH = "C:\nexus-a2a-protocol"
$env:NEXUS_JWT_SECRET = "super-secret-test-key-change-me"
$TOKEN = python -c "import sys; sys.path.insert(0, 'C:/nexus-a2a-protocol'); from shared.nexus_common.auth import mint_jwt; print(mint_jwt('traffic', 'super-secret-test-key-change-me', 36 00))"

Write-Host "🚀 Traffic Generator Starting..." -ForegroundColor Green
Write-Host "   Target: $TRIAGE_URL" -ForegroundColor Cyan
Write-Host "   Rate: ~5 tasks/second" -ForegroundColor Cyan
Write-Host "   Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

$sent = 0
$success = 0
$failed = 0
$startTime = Get-Date

try {
    while ($true) {
        $sent++
        
        # Generate random task data
        $patientId = "Patient/" + (Get-Random -Minimum 10000 -Maximum 99999)
        $complaint = $COMPLAINTS | Get-Random
        $age = Get-Random -Minimum 18 -Maximum 90
        $gender = @("male", "female") | Get-Random
        
        # Build JSON payload
        $payload = @{
            jsonrpc = "2.0"
            method = "tasks/sendSubscribe"
            params = @{
                task = @{
                    patient_ref = $patientId
                    inputs = @{
                        chief_complaint = $complaint
                        age = $age
                        gender = $gender
                    }
                }
            }
            id = "task-$sent"
        } | ConvertTo-Json -Depth 10 -Compress
        
        # Send request
        try {
            $response = Invoke-WebRequest -Uri $TRIAGE_URL `
                -Method POST `
                -Headers @{
                    "Authorization" = "Bearer $TOKEN"
                    "Content-Type" = "application/json"
                } `
                -Body $payload `
                -TimeoutSec 10 `
                -UseBasicParsing
            
            if ($response.StatusCode -eq 200) {
                $success++
            } else {
                $failed++
            }
        } catch {
            $failed++
        }
        
        # Print progress
        $elapsed = ((Get-Date) - $startTime).TotalSeconds
        $rate = if ($elapsed -gt 0) { $sent / $elapsed } else { 0 }
        Write-Host ("`r⏱️  {0:N0}s | Sent: {1} ({2:N1}/s) | ✓ {3} | ✗ {4}     " -f $elapsed, $sent, $rate, $success, $failed) -NoNewline
        
        # Rate limit (~5 per second)
        Start-Sleep -Milliseconds 200
    }
}
catch {
    if ($_.Exception.Message -notlike "*operation was canceled*") {
        Write-Host "`nError: $_" -ForegroundColor Red
    }
}
finally {
    Write-Host "`n"
    Write-Host "✅ Traffic Generator Stopped" -ForegroundColor Green
    $elapsed = ((Get-Date) - $startTime).TotalSeconds
    Write-Host ""
    Write-Host "Final Stats:" -ForegroundColor Cyan
    Write-Host "  Tasks sent: $sent"
    Write-Host "  Successful: $success"
    Write-Host "  Failed: $failed"
    Write-Host ("  Duration: {0:N1}s" -f $elapsed)
    Write-Host ("  Average rate: {0:N2} tasks/second" -f ($sent / $elapsed))
}
