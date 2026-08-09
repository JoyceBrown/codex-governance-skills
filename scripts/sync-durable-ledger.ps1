param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [string]$PlanJson,
    [string]$DriftJson,
    [string]$ReceiptJson,
    [string]$CounterfactualJson,
    [string]$NextAction,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$codexHome = if (-not [string]::IsNullOrWhiteSpace($env:CODEX_HOME)) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$contextState = Join-Path $codexHome 'skills\durable-context\scripts\context_state.py'
if (-not (Test-Path -LiteralPath $contextState)) { throw 'durable-context lifecycle helper is unavailable.' }
$root = (Resolve-Path -LiteralPath $ProjectRoot).Path
$ledger = Join-Path $root '.agent-context'
if (-not (Test-Path -LiteralPath (Join-Path $ledger 'manifest.json'))) { throw 'No durable-context ledger exists at ProjectRoot.' }

function Read-RedactedJson([string]$Value, [string]$Name, [string]$Schema) {
    if ([string]::IsNullOrWhiteSpace($Value)) { return $null }
    if ([Text.Encoding]::UTF8.GetByteCount($Value) -gt 16384) { throw "$Name exceeds 16384 bytes." }
    if ($Value -match '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})') { throw "$Name contains a credential-like value." }
    try { $item = $Value | ConvertFrom-Json } catch { throw "$Name must be valid JSON." }
    if ($null -eq $item -or $item -is [array]) { throw "$Name must contain one object." }
    if ([string]$item.schema -ne $Schema) { throw "$Name has an unexpected schema." }
    return $item
}

$plan = Read-RedactedJson $PlanJson 'PlanJson' 'hcrg-plan-reconciliation-v1'
$drift = Read-RedactedJson $DriftJson 'DriftJson' 'hcrg-drift-report-v1'
$receipt = Read-RedactedJson $ReceiptJson 'ReceiptJson' 'hcrg-completion-receipt-v1'
$counterfactual = Read-RedactedJson $CounterfactualJson 'CounterfactualJson' 'hcrg-counterfactual-review-v1'
if ($null -eq $plan -and $null -eq $drift -and $null -eq $receipt -and $null -eq $counterfactual) { throw 'Provide at least one verified HCRG record.' }

$status = 'active'
$summaryParts = @('HCRG checkpoint')
$riskParts = @()
$verifiedParts = @()
if ($null -ne $plan) {
    $summaryParts += "plan=$($plan.decision):$($plan.proposed_plan_version)"
    if ([string]$plan.status -eq 'blocked_for_clarification') { $status = 'blocked'; $riskParts += 'plan requires clarification' }
    if (-not $NextAction) { $NextAction = [string]$plan.next_action }
}
if ($null -ne $drift) {
    $summaryParts += "drift=$($drift.drift_level):$($drift.recommendation)"
    $verifiedParts += "drift-report:$($drift.drift_level)"
    if ([int]$drift.drift_level -ge 2) { $status = 'blocked'; $riskParts += "drift level $($drift.drift_level)" }
    if (-not $NextAction) { $NextAction = [string]$drift.recommendation }
}
if ($null -ne $receipt) {
    if (-not [bool]$receipt.completion_allowed) { throw 'ReceiptJson does not allow completion.' }
    if ($null -eq $counterfactual -or -not [bool]$counterfactual.review_passed -or [string]$counterfactual.receipt_id -ne [string]$receipt.receipt_id) { throw 'Completion receipt requires a matching passed counterfactual review.' }
    $summaryParts += "receipt=$($receipt.receipt_id)"
    $verifiedParts += "completion-receipt:$($receipt.receipt_id)"
    if ($status -ne 'blocked') { $status = 'complete' }
}
$summaryText = (($summaryParts -join '; ') -replace '[\r\n]+', ' ')
$summary = $summaryText.Substring(0, [Math]::Min(1000, $summaryText.Length))
if ([string]::IsNullOrWhiteSpace($NextAction)) {
    $NextAction = if ($status -eq 'blocked') { 'Clarify or investigate the recorded blocker.' } elseif ($status -eq 'complete') { 'No further action.' } else { 'Continue with the next bounded verification step.' }
}

$verified = ($verifiedParts -join '; ')
$risks = ($riskParts -join '; ')
$result = [ordered]@{
    schema = 'hcrg-durable-ledger-bridge-v1'
    project_root_hash = (([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($root)) | ForEach-Object { $_.ToString('x2') }) -join '').Substring(0, 20)
    checkpoint_status = $status
    summary = $summary
    next_action = $NextAction
    verified = $verified
    risks = $risks
    dry_run = [bool]$DryRun
}
if ($DryRun) { $result | ConvertTo-Json -Depth 6; exit 0 }

$checkpointArgs = @('--root', $root, 'checkpoint', '--summary', $summary, '--next-action', $NextAction, '--status', $status)
if (-not [string]::IsNullOrWhiteSpace($verified)) { $checkpointArgs += @('--verified', $verified) }
if (-not [string]::IsNullOrWhiteSpace($risks)) { $checkpointArgs += @('--risks', $risks) }
& py -3 $contextState @checkpointArgs
if ($LASTEXITCODE -ne 0) { throw "durable-context checkpoint failed with exit code $LASTEXITCODE." }
$result['dry_run'] = $false
$result | ConvertTo-Json -Depth 6
