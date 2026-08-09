param(
    [Parameter(Mandatory = $true)]
    [string]$InputJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$MaxBytes = 16384
if ([Text.Encoding]::UTF8.GetByteCount($InputJson) -gt $MaxBytes) { throw "InputJson exceeds $MaxBytes bytes." }
if ($InputJson -match '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})') { throw 'Credential-like value detected; redact completion evidence.' }
try { $receipt = $InputJson | ConvertFrom-Json } catch { throw 'InputJson must be valid JSON.' }
if ($null -eq $receipt -or $receipt -is [array]) { throw 'InputJson must contain one object.' }

$required = @('task_id', 'plan_version', 'real_user_goal', 'visible_success', 'target_identity', 'target_version', 'source_of_truth', 'artifact_evidence', 'runtime_evidence', 'user_path_evidence', 'identity_verified', 'artifact_status', 'runtime_status', 'source_status', 'user_path_result', 'drift_level', 'verified_at')
foreach ($field in $required) {
    if (-not ($receipt.PSObject.Properties.Name -contains $field)) { throw "Missing completion field '$field'." }
    if ($field -eq 'target_identity') {
        if ($null -eq $receipt.$field -or $receipt.$field -is [array] -or @($receipt.$field.PSObject.Properties).Count -eq 0) { throw 'target_identity must be a non-empty object.' }
        continue
    }
    $values = @($receipt.$field | ForEach-Object { [string]$_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($values.Count -eq 0) { throw "Completion field '$field' must not be empty." }
}
if ($receipt.identity_verified -isnot [bool] -or -not [bool]$receipt.identity_verified) { throw 'identity_verified must be true.' }
foreach ($field in @('artifact_status', 'runtime_status', 'source_status')) {
    if ([string]$receipt.$field -ne 'verified') { throw "$field must be verified." }
}
if ([string]$receipt.user_path_result -notin @('pass', 'passed', 'success', 'succeeded')) { throw 'user_path_result must be a verified pass.' }
$drift = -1
if (-not [int]::TryParse([string]$receipt.drift_level, [ref]$drift) -or $drift -ne 0) { throw 'drift_level must be 0 before completing.' }
$timestamp = [DateTime]::MinValue
if (-not [DateTime]::TryParse([string]$receipt.verified_at, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind, [ref]$timestamp)) { throw 'verified_at must be ISO-8601.' }

$identity = [ordered]@{}
foreach ($property in $receipt.target_identity.PSObject.Properties) {
    $value = [string]$property.Value
    if ([string]::IsNullOrWhiteSpace($value)) { throw "target_identity.$($property.Name) must not be empty." }
    $identity[$property.Name] = $value
}
$canonical = [ordered]@{
    task_id = [string]$receipt.task_id
    plan_version = [string]$receipt.plan_version
    target_identity = $identity
    target_version = [string]$receipt.target_version
    verified_at = $timestamp.ToUniversalTime().ToString('o')
    source_of_truth = @($receipt.source_of_truth)
    artifact_evidence = @($receipt.artifact_evidence)
    runtime_evidence = @($receipt.runtime_evidence)
    user_path_evidence = @($receipt.user_path_evidence)
}
$canonicalJson = $canonical | ConvertTo-Json -Compress -Depth 8
$bytes = [Text.Encoding]::UTF8.GetBytes($canonicalJson)
$hash = [Security.Cryptography.SHA256]::Create()
try { $receiptId = 'hcrg-' + (($hash.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) -join '').Substring(0, 20) } finally { $hash.Dispose() }

[ordered]@{
    schema = 'hcrg-completion-receipt-v1'
    receipt_id = $receiptId
    task_id = [string]$receipt.task_id
    plan_version = [string]$receipt.plan_version
    target_version = [string]$receipt.target_version
    completion_allowed = $true
    verified_at = $timestamp.ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 6
