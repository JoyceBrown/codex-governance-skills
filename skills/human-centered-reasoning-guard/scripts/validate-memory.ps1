param(
    [Parameter(Mandatory = $true)]
    [string]$StorePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$MaxLineBytes = 16384

if (-not (Test-Path -LiteralPath $StorePath)) {
    throw "Memory store does not exist: $StorePath"
}

$required = @('id', 'status', 'trigger', 'action', 'scope', 'project_id', 'source', 'evidence', 'confidence', 'counterexamples', 'supersedes', 'created_at', 'review_at')
$lineNumber = 0
foreach ($line in Get-Content -LiteralPath $StorePath) {
    $lineNumber++
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    if ([Text.Encoding]::UTF8.GetByteCount($line) -gt $MaxLineBytes) {
        throw "Record exceeds $MaxLineBytes bytes at line $lineNumber"
    }
    try { $record = $line | ConvertFrom-Json } catch { throw "Invalid JSON at line $lineNumber" }
    foreach ($field in $required) {
        if (-not ($record.PSObject.Properties.Name -contains $field)) {
            throw "Missing field '$field' at line $lineNumber"
        }
    }
    if ($record.status -notin @('candidate', 'active', 'superseded', 'expired')) {
        throw "Invalid status at line $lineNumber"
    }
    if ($record.scope -notin @('project', 'global')) {
        throw "Invalid scope at line $lineNumber"
    }
    if ($record.scope -eq 'project' -and [string]::IsNullOrWhiteSpace([string]$record.project_id)) {
        throw "Project-scoped record lacks project_id at line $lineNumber"
    }
    if ([string]::IsNullOrWhiteSpace([string]$record.trigger) -or [string]::IsNullOrWhiteSpace([string]$record.action)) {
        throw "Empty trigger or action at line $lineNumber"
    }
    $evidence = @($record.evidence | ForEach-Object { [string]$_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($evidence.Count -eq 0) { throw "Empty evidence at line $lineNumber" }
    $confidence = 0.0
    if (-not [double]::TryParse([string]$record.confidence, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$confidence) -or $confidence -lt 0 -or $confidence -gt 1) {
        throw "Confidence must be between 0 and 1 at line $lineNumber"
    }
    $parsed = [DateTime]::MinValue
    if (-not [DateTime]::TryParse([string]$record.review_at, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind, [ref]$parsed)) {
        throw "Invalid review_at at line $lineNumber"
    }
}

Write-Output "Memory store valid: $lineNumber line(s) checked."
