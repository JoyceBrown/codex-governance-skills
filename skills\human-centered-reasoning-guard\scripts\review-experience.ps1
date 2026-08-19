param(
    [Parameter(Mandatory = $true)]
    [string]$Id,
    [Parameter(Mandatory = $true)]
    [ValidateSet('active', 'superseded', 'expired')]
    [string]$Status,
    [Parameter(Mandatory = $true)]
    [string]$StorePath,
    [switch]$Confirm,
    [string]$Evidence,
    [string]$Counterexample,
    [double]$Confidence,
    [string]$ReviewAt
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $StorePath)) { throw "Memory store does not exist: $StorePath" }
& (Join-Path $PSScriptRoot 'validate-memory.ps1') -StorePath $StorePath | Out-Null

$records = @{}
foreach ($line in Get-Content -LiteralPath $StorePath) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $record = $line | ConvertFrom-Json
    $records[[string]$record.id] = $record
}
if (-not $records.ContainsKey($Id)) { throw "Experience not found: $Id" }
$current = $records[$Id]

if ($Status -eq 'active' -and -not $Confirm) { throw 'Promoting an experience requires -Confirm.' }
$evidenceList = @($current.evidence)
if (-not [string]::IsNullOrWhiteSpace($Evidence)) { $evidenceList += $Evidence }
$counterexamples = @($current.counterexamples)
if (-not [string]::IsNullOrWhiteSpace($Counterexample)) { $counterexamples += $Counterexample }
$nextConfidence = if ($PSBoundParameters.ContainsKey('Confidence')) { $Confidence } else { [double]$current.confidence }
if ($nextConfidence -lt 0 -or $nextConfidence -gt 1) { throw 'Confidence must be between 0 and 1.' }
if ($Status -eq 'active') {
    if ($PSBoundParameters.ContainsKey('Confidence') -and $nextConfidence -lt 0.7) { throw 'Active experiences require confidence >= 0.7.' }
    if (-not $PSBoundParameters.ContainsKey('Confidence')) {
        if ($evidenceList.Count -lt 2) { throw 'Active promotion requires at least two evidence items or an explicit confidence value.' }
        $nextConfidence = [Math]::Max($nextConfidence, 0.7)
    }
}
$nextReview = if ([string]::IsNullOrWhiteSpace($ReviewAt)) { (Get-Date).ToUniversalTime().AddDays(30).ToString('o') } else { $ReviewAt }
if ([Text.Encoding]::UTF8.GetByteCount(($evidenceList -join ' ')) -gt 8192) { throw 'Evidence exceeds the safe size limit.' }
$credentialPattern = '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})'
if (($evidenceList -join ' ') -match $credentialPattern -or ($counterexamples -join ' ') -match $credentialPattern) { throw 'Credential-like value detected; redact it before review.' }

$updated = [ordered]@{
    id = $current.id; status = $Status; trigger = $current.trigger; action = $current.action
    scope = $current.scope; project_id = $current.project_id; source = $current.source
    evidence = @($evidenceList); confidence = $nextConfidence; counterexamples = @($counterexamples)
    supersedes = $current.supersedes; created_at = $current.created_at; review_at = $nextReview
    reviewed_at = (Get-Date).ToUniversalTime().ToString('o')
}
$line = $updated | ConvertTo-Json -Compress -Depth 8
$encoding = New-Object System.Text.UTF8Encoding($false)
$stream = [System.IO.File]::Open($StorePath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
$writer = $null
try {
    $stream.Seek(0, [System.IO.SeekOrigin]::End) | Out-Null
    $writer = New-Object System.IO.StreamWriter($stream, $encoding)
    $writer.WriteLine($line)
    $writer.Flush()
} finally {
    if ($null -ne $writer) { $writer.Dispose() } else { $stream.Dispose() }
}
Write-Output "Experience $Id transitioned to $Status."
