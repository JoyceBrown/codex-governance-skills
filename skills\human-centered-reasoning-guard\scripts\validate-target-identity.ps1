param(
    [Parameter(Mandatory = $true)]
    [string]$ObservedJson,
    [string]$ExpectedJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$required = @('provider', 'model', 'thread', 'client', 'route', 'permission_mode')
$credentialPattern = '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})'
if ([Text.Encoding]::UTF8.GetByteCount($ObservedJson) -gt 8192 -or $ObservedJson -match $credentialPattern) { throw 'Observed identity is oversized or credential-like.' }
try { $observed = $ObservedJson | ConvertFrom-Json } catch { throw 'ObservedJson must be valid JSON.' }
if ($null -eq $observed -or $observed -is [array]) { throw 'ObservedJson must contain one object.' }
foreach ($field in $required) {
    if (-not ($observed.PSObject.Properties.Name -contains $field) -or [string]::IsNullOrWhiteSpace([string]$observed.$field)) { throw "Observed identity is missing '$field'." }
}
$expected = $null
if (-not [string]::IsNullOrWhiteSpace($ExpectedJson)) {
    if ([Text.Encoding]::UTF8.GetByteCount($ExpectedJson) -gt 8192 -or $ExpectedJson -match $credentialPattern) { throw 'Expected identity is oversized or credential-like.' }
    try { $expected = $ExpectedJson | ConvertFrom-Json } catch { throw 'ExpectedJson must be valid JSON.' }
    if ($null -eq $expected -or $expected -is [array]) { throw 'ExpectedJson must contain one object.' }
    foreach ($field in $required) {
        if (-not ($expected.PSObject.Properties.Name -contains $field) -or [string]::IsNullOrWhiteSpace([string]$expected.$field)) { throw "Expected identity is missing '$field'." }
    }
}
$mismatches = @()
if ($null -ne $expected) {
    foreach ($field in $required) { if ([string]$observed.$field -ne [string]$expected.$field) { $mismatches += $field } }
}
[ordered]@{
    schema = 'hcrg-target-identity-v1'
    status = if ($null -eq $expected) { 'observed_only' } elseif ($mismatches.Count -eq 0) { 'matched' } else { 'mismatch' }
    required_fields = $required
    observed = [ordered]@{ provider=[string]$observed.provider; model=[string]$observed.model; thread=[string]$observed.thread; client=[string]$observed.client; route=[string]$observed.route; permission_mode=[string]$observed.permission_mode }
    mismatched_fields = @($mismatches)
    mutation_allowed = [bool]($null -ne $expected -and $mismatches.Count -eq 0)
} | ConvertTo-Json -Depth 6
