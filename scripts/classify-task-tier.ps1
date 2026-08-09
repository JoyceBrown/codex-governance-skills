param(
    [Parameter(Mandatory = $true)]
    [string]$InputJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$MaxBytes = 8192
if ([Text.Encoding]::UTF8.GetByteCount($InputJson) -gt $MaxBytes) { throw "InputJson exceeds $MaxBytes bytes." }
if ($InputJson -match '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})') { throw 'Credential-like value detected; classify redacted task facts only.' }
try { $task = $InputJson | ConvertFrom-Json } catch { throw 'InputJson must be valid JSON.' }
if ($null -eq $task -or $task -is [array]) { throw 'InputJson must contain one object.' }

$required = @('request_kind', 'boundary_count', 'attempts_same_symptom', 'user_reports_unchanged', 'evidence_conflict', 'interrupted', 'external_state', 'risky_action', 'destructive_action')
foreach ($field in $required) { if (-not ($task.PSObject.Properties.Name -contains $field)) { throw "Missing tier field '$field'." } }
$kinds = @('question', 'read_only', 'change', 'debug', 'deployment', 'migration', 'deletion')
if ([string]$task.request_kind -notin $kinds) { throw "Invalid request_kind: $($task.request_kind)" }
$boundaries = 0
$attempts = 0
if (-not [int]::TryParse([string]$task.boundary_count, [ref]$boundaries) -or $boundaries -lt 0) { throw 'boundary_count must be a non-negative integer.' }
if (-not [int]::TryParse([string]$task.attempts_same_symptom, [ref]$attempts) -or $attempts -lt 0) { throw 'attempts_same_symptom must be a non-negative integer.' }
foreach ($field in @('user_reports_unchanged', 'evidence_conflict', 'interrupted', 'external_state', 'risky_action', 'destructive_action')) {
    if ($task.$field -isnot [bool]) { throw "$field must be true or false." }
}

$tier = 'light'
$reasons = @()
if ($attempts -ge 2 -or [bool]$task.user_reports_unchanged -or [bool]$task.evidence_conflict) {
    $tier = 'reset'
    $reasons += 'failed symptom, unchanged result, or conflicting evidence'
} elseif ([string]$task.request_kind -in @('debug', 'deployment', 'migration', 'deletion') -or $boundaries -gt 1 -or [bool]$task.interrupted -or [bool]$task.external_state -or [bool]$task.risky_action -or [bool]$task.destructive_action) {
    $tier = 'full'
    $reasons += 'cross-boundary, risky, interrupted, or stateful task'
} else {
    $reasons += 'self-contained low-risk task'
}

$minimum = switch ($tier) {
    'light' { @('real goal', 'visible success', 'authorization', 'one verification') }
    'full' { @('task card', 'fact gate', 'goal gate', 'plan/drift check', 'real user-path verification') }
    'reset' { @('record exact symptom', 'reopen hypotheses', 'one discriminating observation', 'no causal write before evidence') }
}
[ordered]@{
    schema = 'hcrg-task-tier-v1'
    tier = $tier
    reasons = @($reasons | Select-Object -Unique)
    minimum_requirements = $minimum
} | ConvertTo-Json -Depth 6
