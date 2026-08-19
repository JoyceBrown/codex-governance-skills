param(
    [Parameter(Mandatory = $true)]
    [string]$CardPath,
    [Parameter(Mandatory = $true)]
    [ValidateSet('planning', 'investigating', 'ready_to_write', 'executing', 'verifying', 'paused', 'blocked', 'complete')]
    [string]$NextState,
    [Parameter(Mandatory = $true)]
    [string]$Reason,
    [string]$HypothesisId,
    [string]$Result,
    [string]$VerifiedAt
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'validate-task-card.ps1') -CardPath $CardPath | Out-Null
$card = Get-Content -Raw -LiteralPath $CardPath | ConvertFrom-Json
$allowed = @{
    planning = @('investigating', 'paused', 'blocked')
    investigating = @('ready_to_write', 'paused', 'blocked')
    ready_to_write = @('executing', 'paused', 'blocked')
    executing = @('verifying', 'paused', 'blocked')
    verifying = @('complete', 'investigating', 'executing', 'paused', 'blocked')
    paused = @('investigating', 'ready_to_write', 'blocked')
    blocked = @('investigating', 'paused')
    complete = @()
}
if ($NextState -notin $allowed[[string]$card.state]) { throw "Illegal state transition: $($card.state) -> $NextState" }
if ([string]::IsNullOrWhiteSpace($Reason)) { throw 'Reason is required for every state transition.' }
if ($NextState -eq 'executing' -and [string]::IsNullOrWhiteSpace($HypothesisId)) { throw 'HypothesisId is required before executing.' }
if ($NextState -eq 'complete' -and [string]::IsNullOrWhiteSpace($VerifiedAt)) { throw 'VerifiedAt is required before completing.' }

$updated = [ordered]@{}
foreach ($property in $card.PSObject.Properties) { $updated[$property.Name] = $property.Value }
$updated['state'] = $NextState
$updated['state_reason'] = $Reason
$updated['updated_at'] = (Get-Date).ToUniversalTime().ToString('o')
if ($NextState -eq 'executing') {
    $updated['attempts'] = [int]$card.attempts + 1
    $updated['attempt_id'] = [guid]::NewGuid().ToString('N')
    $updated['hypothesis_id'] = $HypothesisId
}
if (-not [string]::IsNullOrWhiteSpace($Result)) { $updated['last_result'] = $Result }
if ($NextState -eq 'complete') { $updated['last_verified_at'] = $VerifiedAt }

$tempPath = "$CardPath.$([guid]::NewGuid().ToString('N')).tmp"
try {
    ($updated | ConvertTo-Json -Depth 12) | Set-Content -LiteralPath $tempPath -Encoding UTF8
    & (Join-Path $PSScriptRoot 'validate-task-card.ps1') -CardPath $tempPath | Out-Null
    Move-Item -LiteralPath $tempPath -Destination $CardPath -Force
} finally {
    if (Test-Path -LiteralPath $tempPath) { [IO.File]::Delete($tempPath) }
}
Write-Output "Task state transitioned: $($card.state) -> $NextState"
