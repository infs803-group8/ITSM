param([string]$ComposeFile = "docker-compose.local.yml")
$ErrorActionPreference = "Stop"
$repositoryRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Push-Location $repositoryRoot
try {
  docker compose -f $ComposeFile down --volumes
  docker compose -f $ComposeFile up -d mysql
} finally {
  Pop-Location
}
