# Phase 0.2 smoke test against a live Reverie API.
# Usage:  .venv\Scripts\python.exe -m reverie_api    (in another terminal)
#         pwsh scripts\smoke.ps1
$ErrorActionPreference = "Stop"

$base = "http://127.0.0.1:8000"
$runId = [guid]::NewGuid().ToString()
$sessionId = [guid]::NewGuid().ToString()

Write-Host "1) Health"
Invoke-RestMethod "$base/health" | ConvertTo-Json -Compress | Write-Host

Write-Host "`n2) Create run $runId"
$run = @{
    runId = $runId
    sessionId = $sessionId
    agentId = "agent-smoke"
    runtime = "openai-agents"
    startedAt = [int64](([DateTimeOffset]::UtcNow).ToUnixTimeMilliseconds())
    goal = "smoke test"
} | ConvertTo-Json
Invoke-RestMethod "$base/api/v1/runs" -Method POST -Body $run -ContentType "application/json" | ConvertTo-Json -Compress | Write-Host

Write-Host "`n3) Post a batch of 3 events"
$ts = [int64](([DateTimeOffset]::UtcNow).ToUnixTimeMilliseconds())
$events = @(
    @{
        id = [guid]::NewGuid().ToString()
        type = "goal.created"
        runId = $runId
        sessionId = $sessionId
        agentId = "agent-smoke"
        parentId = $null
        depth = 0
        timestamp = $ts
        durationMs = $null
        payload = @{ "_type" = "goal"; intent = "research"; priority = "high"; context = "" }
        salience = $null
        anomaly = $false
        schemaVersion = "1.0"
    },
    @{
        id = [guid]::NewGuid().ToString()
        type = "tool.called"
        runId = $runId
        sessionId = $sessionId
        agentId = "agent-smoke"
        parentId = $null
        depth = 1
        timestamp = $ts + 1
        durationMs = $null
        payload = @{
            "_type" = "tool"; toolName = "search_web"; args = @{ query = "x" };
            result = $null; latencyMs = 0; tokenCost = $null; success = $true; errorMessage = $null
        }
        salience = $null
        anomaly = $false
        schemaVersion = "1.0"
    },
    @{
        id = [guid]::NewGuid().ToString()
        type = "tool.returned"
        runId = $runId
        sessionId = $sessionId
        agentId = "agent-smoke"
        parentId = $null
        depth = 1
        timestamp = $ts + 50
        durationMs = 50.0
        payload = @{
            "_type" = "tool"; toolName = "search_web"; args = @{ query = "x" };
            result = @{ hits = 3 }; latencyMs = 50.0; tokenCost = 120; success = $true; errorMessage = $null
        }
        salience = $null
        anomaly = $false
        schemaVersion = "1.0"
    }
) | ConvertTo-Json -Depth 8
Invoke-RestMethod "$base/api/v1/events/batch" -Method POST -Body $events -ContentType "application/json" | ConvertTo-Json -Compress | Write-Host

Write-Host "`n4) Re-fetch run (aggregates should be updated)"
Invoke-RestMethod "$base/api/v1/runs/$runId" | ConvertTo-Json -Compress | Write-Host

Write-Host "`n5) Fetch events"
$evts = Invoke-RestMethod "$base/api/v1/runs/$runId/events"
Write-Host ("  total returned: " + $evts.Count)
$evts | ForEach-Object { Write-Host ("  - " + $_.type + " @" + $_.timestamp) }

Write-Host "`nSmoke test OK."
