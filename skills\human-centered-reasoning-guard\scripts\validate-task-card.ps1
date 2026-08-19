param(
    [Parameter(Mandatory = $true)]
    [string]$CardPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$MaxBytes = 16384
$required = @('task_id', 'plan_version', 'state', 'state_reason', 'real_user_goal', 'visible_success', 'authorization', 'forbidden_actions', 'verified_facts', 'unknowns', 'target_identity', 'target_version', 'source_of_truth', 'baseline', 'attempts', 'attempt_id', 'hypothesis_id', 'last_result', 'last_verified_at', 'rollback_ref', 'next_action', 'updated_at')

if (-not (Test-Path -LiteralPath $CardPath)) { throw "Task card does not exist: $CardPath" }
$json = Get-Content -Raw -LiteralPath $CardPath
if ([Text.Encoding]::UTF8.GetByteCount($json) -gt $MaxBytes) { throw "Task card exceeds $MaxBytes bytes." }
try { $card = $json | ConvertFrom-Json } catch { throw 'Task card is not valid JSON.' }

foreach ($field in $required) {
    if (-not ($card.PSObject.Properties.Name -contains $field)) { throw "Missing field '$field'." }
}
foreach ($field in @('task_id', 'plan_version', 'real_user_goal', 'visible_success', 'target_version', 'next_action', 'updated_at')) {
    if ([string]::IsNullOrWhiteSpace([string]$card.$field)) { throw "Field '$field' must not be empty." }
}
$states = @('planning', 'investigating', 'ready_to_write', 'executing', 'verifying', 'paused', 'blocked', 'complete')
if ($card.state -notin $states) { throw "Invalid state: $($card.state)" }
if ([string]::IsNullOrWhiteSpace([string]$card.state_reason)) { throw 'state_reason must not be empty.' }
if (@($card.authorization).Count -eq 0) { throw 'authorization must not be empty.' }
if (@($card.baseline).Count -eq 0) { throw 'baseline must contain at least one observation.' }
if (@($card.source_of_truth).Count -eq 0) { throw 'source_of_truth must contain at least one item.' }
$attempts = 0
if (-not [int]::TryParse([string]$card.attempts, [ref]$attempts) -or $attempts -lt 0) { throw 'attempts must be a non-negative integer.' }
$credentialPattern = '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})'
if ($json -match $credentialPattern) { throw 'Credential-like value detected in task card.' }
$parsed = [DateTime]::MinValue
if (-not [DateTime]::TryParse([string]$card.updated_at, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind, [ref]$parsed)) { throw 'updated_at must be ISO-8601.' }
if (-not [string]::IsNullOrWhiteSpace([string]$card.last_verified_at) -and -not [DateTime]::TryParse([string]$card.last_verified_at, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind, [ref]$parsed)) { throw 'last_verified_at must be ISO-8601 or null.' }
Write-Output "Task card valid: $($card.task_id)"
