param([Parameter(Mandatory = $true)][string]$CommitSha)
$ErrorActionPreference = "Stop"
Write-Host "TODO: build frontend:$CommitSha, push ECR, register task definition, update frontend ECS only."
