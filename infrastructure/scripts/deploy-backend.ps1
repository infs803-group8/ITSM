param([Parameter(Mandatory = $true)][string]$CommitSha)
$ErrorActionPreference = "Stop"
Write-Host "TODO: build backend:$CommitSha, push ECR, register task definition, update backend ECS only."
