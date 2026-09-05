param([Parameter(Mandatory = $true)][string]$BaseUrl)
$ErrorActionPreference = "Stop"
$response = Invoke-RestMethod -Uri "$($BaseUrl.TrimEnd('/'))/api/v1/health" -TimeoutSec 30
if ($response.data.status -ne "ok" -or $response.data.checks.database -ne "ok") {
    throw "Health check failed."
}
Write-Host "Backend and database health checks passed."
