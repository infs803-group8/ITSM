param([Parameter(Mandatory = $true)][string]$CommitSha, [string]$ConfigPath = $env:DEPLOY_CONFIG_PATH)
$ErrorActionPreference = "Stop"
& python "$PSScriptRoot/deploy.py" --component all --commit $CommitSha --config $ConfigPath
if ($LASTEXITCODE -ne 0) { throw "Final deployment failed ($LASTEXITCODE)." }
