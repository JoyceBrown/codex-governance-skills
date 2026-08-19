param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('edit', 'write', 'destructive', 'routine')]
    [string]$ActionType,
    [Parameter(Mandatory = $true)]
    [string]$FactsJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$MaxBytes = 8192
if ([Text.Encoding]::UTF8.GetByteCount($FactsJson) -gt $MaxBytes) { throw "FactsJson exceeds $MaxBytes bytes." }
if ($FactsJson -match '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})') { throw 'Credential-like value detected; redact facts before gating.' }
try { $facts = $FactsJson | ConvertFrom-Json } catch { throw 'FactsJson must be valid JSON.' }
if ($null -eq $facts -or $facts -is [array]) { throw 'FactsJson must contain one object.' }

$required = @{
    routine = @('current_user_instruction', 'purpose')
    edit = @('current_user_instruction', 'target_files', 'callers_or_consumers', 'public_surface', 'source_of_truth', 'baseline')
    write = @('current_user_instruction', 'target_path', 'existing_capability_search', 'callers_or_consumers', 'source_of_truth', 'baseline')
    destructive = @('current_user_instruction', 'exact_targets', 'authorization_scope', 'rollback', 'source_of_truth', 'baseline')
}
foreach ($field in $required[$ActionType]) {
    if (-not ($facts.PSObject.Properties.Name -contains $field)) { throw "Fact gate blocked ${ActionType}: missing $field" }
    $value = @($facts.$field | ForEach-Object { [string]$_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($value.Count -eq 0) { throw "Fact gate blocked ${ActionType}: empty $field" }
}
Write-Output "Fact gate passed: $ActionType"
