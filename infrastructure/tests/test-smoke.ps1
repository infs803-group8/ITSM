$ErrorActionPreference = 'Stop'
$global:ItsmSmokeTestResponse = @{ data = @{ status = 'ok'; checks = @{ database = 'ok' } } }
function Invoke-RestMethod {
    param([string]$Uri, [int]$TimeoutSec)
    if ($Uri -ne 'https://review.invalid/api/v1/health') { throw "Unexpected URL: $Uri" }
    return $global:ItsmSmokeTestResponse
}
& "$PSScriptRoot/../scripts/run-smoke-tests.ps1" -BaseUrl 'https://review.invalid/'
foreach ($badResponse in @(@{ status = 'ok' }, @{ data = @{ status = 'ok'; checks = @{ database = 'failed' } } })) {
    $global:ItsmSmokeTestResponse = $badResponse
    $rejected = $false
    try { & "$PSScriptRoot/../scripts/run-smoke-tests.ps1" -BaseUrl 'https://review.invalid/' }
    catch { $rejected = $true }
    if (-not $rejected) { throw 'Invalid health response was accepted' }
}
function python { $global:LASTEXITCODE = 17 }
foreach ($name in @('deploy-backend', 'deploy-frontend', 'deploy-final', 'run-database-bootstrap')) {
    $rejected = $false
    try { & "$PSScriptRoot/../scripts/$name.ps1" -CommitSha ('a' * 40) -ConfigPath 'unused.json' }
    catch { $rejected = $true }
    if (-not $rejected) { throw "$name did not propagate deployment failure" }
}
$global:LASTEXITCODE = 0
Remove-Variable -Name ItsmSmokeTestResponse -Scope Global
Write-Host 'Smoke contract and deployment exit-code checks passed.'
