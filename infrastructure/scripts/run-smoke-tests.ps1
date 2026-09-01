param([Parameter(Mandatory = $true)][string]$BaseUrl)
$ErrorActionPreference = "Stop"
$response = Invoke-RestMethod -Uri "$BaseUrl/api/v1/health"
if ($response.status -ne "ok") { throw "Health check failed." }
