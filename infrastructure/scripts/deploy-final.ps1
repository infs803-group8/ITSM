param([Parameter(Mandatory = $true)][string]$CommitSha)
$ErrorActionPreference = "Stop"
& $PSScriptRoot\deploy-backend.ps1 -CommitSha $CommitSha
& $PSScriptRoot\deploy-frontend.ps1 -CommitSha $CommitSha
