param([switch]$Confirmed)
$ErrorActionPreference = "Stop"
if (-not $Confirmed) { throw "Pass -Confirmed only after reviewing the exact final workspace." }
Write-Host "Review and run terraform destroy from infrastructure/terraform/final."
