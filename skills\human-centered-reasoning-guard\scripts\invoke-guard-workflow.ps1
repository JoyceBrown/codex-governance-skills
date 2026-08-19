param(
    [Parameter(Mandatory = $true)]
    [string]$InputJson,
    [string]$CardPath,
    [string]$IdentityJson,
    [string]$ExpectedIdentityJson,
    [string]$DriftJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$tierScript = Join-Path $PSScriptRoot 'classify-task-tier.ps1'
$preflight = Join-Path $PSScriptRoot 'preflight-task.ps1'
$identityScript = Join-Path $PSScriptRoot 'validate-target-identity.ps1'
$credentialPattern = '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})'
if ([Text.Encoding]::UTF8.GetByteCount($InputJson) -gt 8192 -or $InputJson -match $credentialPattern) { throw 'InputJson is oversized or credential-like.' }
$tier = & $tierScript -InputJson $InputJson | ConvertFrom-Json
$decision = 'inspect_only'
$mutationAllowed = $false
$blocks = @()
$next = @($tier.minimum_requirements)
$identityStatus = 'not_provided'
$driftStatus = 'not_provided'

if ($tier.tier -in @('full','reset')) {
    if ([string]::IsNullOrWhiteSpace($CardPath)) {
        $blocks += 'validated task card required before stateful or risky work'
        $decision = 'prepare_task_card'
    } else {
        & $preflight -CardPath $CardPath | Out-Null
        $decision = 'preflight_passed'
    }
    if ([string]::IsNullOrWhiteSpace($IdentityJson)) {
        $blocks += 'target identity must be observed before cross-client or provider work'
    } else {
        $identityResult = & $identityScript -ObservedJson $IdentityJson -ExpectedJson $ExpectedIdentityJson | ConvertFrom-Json
        $identityStatus = [string]$identityResult.status
        if ($identityStatus -ne 'matched') { $blocks += "target identity status=$identityStatus" }
    }
}
if (-not [string]::IsNullOrWhiteSpace($DriftJson)) {
    try { $drift = $DriftJson | ConvertFrom-Json } catch { throw 'DriftJson must be valid JSON.' }
    if ($null -eq $drift.drift_level) { throw 'DriftJson is missing drift_level.' }
    $driftStatus = "level-$([int]$drift.drift_level)"
    if ([int]$drift.drift_level -ge 2) { $blocks += 'drift level 2 or 3 blocks the current causal patch path'; $decision = 'investigate_boundary' }
    elseif ([int]$drift.drift_level -eq 1) { $blocks += 'rebaseline before writing'; $decision = 'rebaseline' }
}
if ($tier.tier -eq 'reset') {
    $blocks += 'reset tier requires one discriminating observation and a new hypothesis'
    $decision = 'reset_and_investigate'
}
if ($blocks.Count -eq 0 -and $tier.tier -eq 'light') {
    $decision = 'light_verification'
    $mutationAllowed = $false
}
if ($blocks.Count -eq 0 -and $tier.tier -eq 'full' -and -not [string]::IsNullOrWhiteSpace($CardPath) -and $identityStatus -eq 'matched' -and $driftStatus -in @('not_provided','level-0')) {
    $decision = 'ready_for_bounded_action'
    $mutationAllowed = $true
}
[ordered]@{
    schema = 'hcrg-workflow-decision-v1'
    tier = [string]$tier.tier
    reasons = @($tier.reasons)
    decision = $decision
    mutation_allowed = $mutationAllowed
    blocks = @($blocks | Select-Object -Unique)
    identity_status = $identityStatus
    drift_status = $driftStatus
    required_steps = $next
    out_of_scope = @('parallel human sessions','unverified memory promotion','bypassing durable-context','provider or network mutation without explicit authorization')
} | ConvertTo-Json -Depth 8
