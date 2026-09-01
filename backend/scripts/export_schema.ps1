param(
  [Parameter(Mandatory = $true)][string]$DatabaseHost,
  [Parameter(Mandatory = $true)][string]$DatabaseUser,
  [string]$DatabaseName = "service_desk"
)
$ErrorActionPreference = "Stop"
mysqldump --host=$DatabaseHost --user=$DatabaseUser --password --no-data --routines --triggers $DatabaseName
