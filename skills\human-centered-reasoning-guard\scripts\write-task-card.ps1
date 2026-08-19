param(
    [Parameter(Mandatory = $true)]
    [string]$InputJson,
    [string]$CardPath = (Join-Path (Get-Location) '.agent-context\task-card.json')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$MaxBytes = 16384
if ([Text.Encoding]::UTF8.GetByteCount($InputJson) -gt $MaxBytes) { throw "Task card exceeds $MaxBytes bytes." }
if ($InputJson -match '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})') { throw 'Credential-like value detected; redact the task card before writing.' }
try { $card = $InputJson | ConvertFrom-Json } catch { throw 'InputJson must be valid JSON.' }
if ($null -eq $card -or $card -is [array]) { throw 'InputJson must contain one object.' }

foreach ($field in @('task_id', 'plan_version', 'real_user_goal', 'visible_success', 'authorization', 'forbidden_actions', 'verified_facts', 'unknowns', 'target_identity', 'target_version', 'source_of_truth', 'baseline', 'attempts', 'next_action')) {
    if (-not ($card.PSObject.Properties.Name -contains $field)) { throw "Missing field '$field'." }
}

$output = [ordered]@{}
foreach ($property in $card.PSObject.Properties) { $output[$property.Name] = $property.Value }
$defaults = [ordered]@{
    state = 'planning'
    state_reason = 'initial task card'
    attempt_id = $null
    hypothesis_id = $null
    last_result = $null
    last_verified_at = $null
    rollback_ref = $null
}
foreach ($property in $defaults.Keys) {
    if (-not ($output.Keys -contains $property)) { $output[$property] = $defaults[$property] }
}
$output['updated_at'] = (Get-Date).ToUniversalTime().ToString('o')
$parent = Split-Path -Parent $CardPath
if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
$tempPath = "$CardPath.$([guid]::NewGuid().ToString('N')).tmp"
try {
    ($output | ConvertTo-Json -Depth 12) | Set-Content -LiteralPath $tempPath -Encoding UTF8
    & (Join-Path $PSScriptRoot 'validate-task-card.ps1') -CardPath $tempPath | Out-Null
    if (Test-Path -LiteralPath $CardPath) {
        Move-Item -LiteralPath $tempPath -Destination $CardPath -Force
    } else {
        Move-Item -LiteralPath $tempPath -Destination $CardPath
    }
} finally {
    if (Test-Path -LiteralPath $tempPath) { [IO.File]::Delete($tempPath) }
}
Write-Output "Task card valid: $($output.task_id)"
