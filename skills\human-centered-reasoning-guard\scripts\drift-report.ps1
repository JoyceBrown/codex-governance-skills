param(
    [Parameter(Mandatory = $true)]
    [string]$InputJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$MaxBytes = 16384
if ([Text.Encoding]::UTF8.GetByteCount($InputJson) -gt $MaxBytes) { throw "InputJson exceeds $MaxBytes bytes." }
if ($InputJson -match '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})') { throw 'Credential-like value detected; redact drift facts.' }
try { $state = $InputJson | ConvertFrom-Json } catch { throw 'InputJson must be valid JSON.' }
if ($null -eq $state -or $state -is [array]) { throw 'InputJson must contain one object.' }

$required = @('task_id', 'plan_version', 'target_version', 'goal_status', 'plan_status', 'artifact_status', 'runtime_status', 'identity_status', 'source_status', 'authorization_status', 'user_status', 'evidence')
foreach ($field in $required) {
    if (-not ($state.PSObject.Properties.Name -contains $field)) { throw "Missing drift field '$field'." }
    if ([string]::IsNullOrWhiteSpace([string]$state.$field) -and $field -ne 'evidence') { throw "Drift field '$field' must not be empty." }
}
$sets = @{
    goal_status = @('aligned', 'refined', 'conflict', 'unknown')
    plan_status = @('current', 'stale', 'unknown')
    artifact_status = @('matches_target', 'mismatch', 'unknown')
    runtime_status = @('matches_target', 'mismatch', 'unknown')
    identity_status = @('matches_target', 'mismatch', 'unknown')
    source_status = @('authoritative', 'stale', 'conflict', 'unknown')
    authorization_status = @('authorized', 'missing', 'conflict', 'unknown')
    user_status = @('pass', 'fail', 'unknown')
}
foreach ($field in $sets.Keys) { if ([string]$state.$field -notin $sets[$field]) { throw "Invalid ${field}: $($state.$field)" } }
if (@($state.evidence).Count -eq 0) { throw 'evidence must contain at least one item.' }

$level = 0
$reasons = @()
if ([string]$state.goal_status -eq 'conflict' -or [string]$state.authorization_status -in @('missing', 'conflict', 'unknown') -or [string]$state.identity_status -in @('mismatch', 'unknown') -or [string]$state.source_status -eq 'conflict') {
    $level = 3
    $reasons += 'goal, authorization, identity, or source conflict'
}
if ([string]$state.artifact_status -eq 'mismatch' -or [string]$state.runtime_status -eq 'mismatch' -or [string]$state.user_status -eq 'fail') {
    $level = [math]::Max($level, 2)
    $reasons += 'artifact, runtime, or user observation mismatch'
}
if ([string]$state.goal_status -in @('refined', 'unknown') -or [string]$state.plan_status -in @('stale', 'unknown') -or [string]$state.artifact_status -eq 'unknown' -or [string]$state.runtime_status -eq 'unknown' -or [string]$state.source_status -in @('stale', 'unknown') -or [string]$state.user_status -eq 'unknown') {
    $level = [math]::Max($level, 1)
    $reasons += 'evidence is stale or incomplete'
}

$recommendation = switch ($level) {
    0 { if ([string]$state.user_status -eq 'pass') { 'safe_to_complete' } else { 'continue_bounded_work' } }
    1 { 'rebaseline_before_write' }
    2 { 'stop_current_patch_and_investigate_boundary' }
    3 { 'block_mutation_and_clarify' }
}
$output = [ordered]@{
    schema = 'hcrg-drift-report-v1'
    task_id = [string]$state.task_id
    plan_version = [string]$state.plan_version
    target_version = [string]$state.target_version
    drift_level = $level
    reasons = @($reasons | Select-Object -Unique)
    recommendation = $recommendation
    completion_allowed = ($level -eq 0 -and [string]$state.user_status -eq 'pass')
    evidence = @($state.evidence)
}
$output | ConvertTo-Json -Depth 8
