param(
    [Parameter(Mandatory = $true)]
    [string]$ReceiptJson,
    [Parameter(Mandatory = $true)]
    [string]$DriftJson,
    [Parameter(Mandatory = $true)]
    [string]$ReviewJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
foreach ($input in @($ReceiptJson, $DriftJson, $ReviewJson)) {
    if ([Text.Encoding]::UTF8.GetByteCount($input) -gt 16384) { throw 'Counterfactual input exceeds 16384 bytes.' }
    if ($input -match '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})') { throw 'Credential-like value detected; redact review evidence.' }
}
$receiptValidator = Join-Path $PSScriptRoot 'validate-completion-receipt.ps1'
$receiptOutput = & $receiptValidator -InputJson $ReceiptJson
$receipt = $receiptOutput | ConvertFrom-Json
try { $drift = $DriftJson | ConvertFrom-Json; $review = $ReviewJson | ConvertFrom-Json } catch { throw 'Counterfactual inputs must be valid JSON.' }
if ([string]$drift.schema -ne 'hcrg-drift-report-v1' -or [int]$drift.drift_level -ne 0) { throw 'Counterfactual review requires a level 0 drift report.' }
if ([string]$review.task_id -ne [string]$receipt.task_id) { throw 'Review task_id must match the completion receipt.' }
if ($null -eq $review.checks -or $review.checks -isnot [array]) { throw 'ReviewJson.checks must be an array.' }
$requiredKinds = @('wrong_target_or_identity', 'stale_artifact_or_runtime', 'source_divergence_or_duplicate', 'user_path_after_refresh', 'rejected_path_no_false_success')
$seen = @{}
foreach ($check in @($review.checks)) {
    if ($null -eq $check -or $check -is [array]) { throw 'Each counterfactual check must be an object.' }
    foreach ($field in @('kind', 'result', 'evidence_ref')) { if (-not ($check.PSObject.Properties.Name -contains $field) -or [string]::IsNullOrWhiteSpace([string]$check.$field)) { throw "Counterfactual check is missing $field." } }
    $kind = [string]$check.kind
    if ($kind -notin $requiredKinds) { throw "Unknown counterfactual check kind: $kind" }
    if ($seen.ContainsKey($kind)) { throw "Duplicate counterfactual check kind: $kind" }
    if ([string]$check.result -notin @('pass', 'passed')) { throw "Counterfactual check '$kind' did not pass." }
    $seen[$kind] = $true
}
foreach ($kind in $requiredKinds) { if (-not $seen.ContainsKey($kind)) { throw "Missing counterfactual check: $kind" } }
$seed = "$($receipt.receipt_id)|$($drift.plan_version)|$($review.checks.Count)"
$hash = [Security.Cryptography.SHA256]::Create()
try { $reviewId = 'hcrg-cf-' + (($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($seed)) | ForEach-Object { $_.ToString('x2') }) -join '').Substring(0, 20) } finally { $hash.Dispose() }
[ordered]@{
    schema = 'hcrg-counterfactual-review-v1'
    review_id = $reviewId
    receipt_id = [string]$receipt.receipt_id
    task_id = [string]$receipt.task_id
    review_passed = $true
} | ConvertTo-Json -Depth 6
