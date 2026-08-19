param(
    [Parameter(Mandatory = $true)]
    [string]$Query,
    [Parameter(Mandatory = $true)]
    [string]$StorePath,
    [string]$ProjectId,
    [int]$Limit = 5,
    [switch]$IncludeCandidates,
    [switch]$DisableFastPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($Limit -lt 1 -or $Limit -gt 20) { throw 'Limit must be between 1 and 20.' }
if (-not (Test-Path -LiteralPath $StorePath)) { throw "Memory store does not exist: $StorePath" }

$queryText = $Query.ToLowerInvariant()
$terms = @($queryText -split '[\s,.;:!?/\\|()\[\]{}"''`]+' | Where-Object { $_.Length -ge 2 })
foreach ($match in [regex]::Matches($queryText, '[\u4e00-\u9fff]{2,}')) {
    $terms += $match.Value
    for ($index = 0; $index -lt $match.Value.Length - 1; $index++) { $terms += $match.Value.Substring($index, 2) }
}
$terms = @($terms | Where-Object { $_.Length -ge 2 } | Select-Object -Unique)
if ($terms.Count -eq 0) { throw 'Query must contain at least one searchable term.' }

$python = Get-Command py.exe -ErrorAction SilentlyContinue
$fastRetriever = Join-Path $PSScriptRoot 'retrieve-experience-fast.py'
if (-not $DisableFastPath -and $null -ne $python -and (Test-Path -LiteralPath $fastRetriever -PathType Leaf)) {
    $fastArgs = @('-3', $fastRetriever, '--query', $Query, '--store-path', $StorePath, '--limit', [string]$Limit)
    if (-not [string]::IsNullOrWhiteSpace($ProjectId)) { $fastArgs += @('--project-id', $ProjectId) }
    if ($IncludeCandidates) { $fastArgs += '--include-candidates' }
    & $python.Source @fastArgs
    if ($LASTEXITCODE -ne 0) { throw "Fast experience retrieval failed with exit code $LASTEXITCODE." }
    return
}

$required = @('id', 'status', 'trigger', 'action', 'scope', 'project_id', 'source', 'evidence', 'confidence', 'counterexamples', 'supersedes', 'created_at', 'review_at')
$raw = Get-Content -LiteralPath $StorePath -Raw
$nonEmptyLines = @([regex]::Split($raw, '\r?\n') | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
if ($nonEmptyLines.Count -eq 0) { throw 'Memory store is empty.' }
$nonEmptyLines[0] = $nonEmptyLines[0].TrimStart([char]0xFEFF)
$maxLineBytes = 16384
foreach ($line in $nonEmptyLines) {
    if ([Text.Encoding]::UTF8.GetByteCount($line) -gt $maxLineBytes) { throw "Record exceeds $maxLineBytes bytes." }
}
try {
    Add-Type -AssemblyName System.Web.Extensions -ErrorAction Stop
    $serializer = New-Object System.Web.Script.Serialization.JavaScriptSerializer
    $serializer.MaxJsonLength = 104857600
    # Parse the JSONL as one JSON array with the platform serializer to avoid a parser process per record.
    $records = @($serializer.DeserializeObject(('[{0}]' -f ($nonEmptyLines -join ','))))
} catch {
    throw 'Memory store contains invalid JSON.'
}
$lineNumber = 0
foreach ($record in $records) {
    $lineNumber++
    foreach ($field in $required) {
        if (-not ($record -is [Collections.IDictionary]) -or -not $record.ContainsKey($field)) { throw "Missing field '$field' at record $lineNumber" }
    }
    if ([string]$record['status'] -notin @('candidate', 'active', 'superseded', 'expired')) { throw "Invalid status at record $lineNumber" }
    if ([string]$record['scope'] -notin @('project', 'global')) { throw "Invalid scope at record $lineNumber" }
    if ([string]$record['scope'] -eq 'project' -and [string]::IsNullOrWhiteSpace([string]$record['project_id'])) { throw "Project-scoped record lacks project_id at record $lineNumber" }
    if ([string]::IsNullOrWhiteSpace([string]$record['trigger']) -or [string]::IsNullOrWhiteSpace([string]$record['action'])) { throw "Empty trigger or action at record $lineNumber" }
    if (@($record['evidence'] | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }).Count -eq 0) { throw "Empty evidence at record $lineNumber" }
    $confidence = 0.0
    if (-not [double]::TryParse([string]$record['confidence'], [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$confidence) -or $confidence -lt 0 -or $confidence -gt 1) { throw "Confidence must be between 0 and 1 at record $lineNumber" }
    $reviewAt = [DateTime]::MinValue
    if (-not [DateTime]::TryParse([string]$record['review_at'], [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind, [ref]$reviewAt)) { throw "Invalid review_at at record $lineNumber" }
}

$latest = @{}
foreach ($record in $records) {
    $latest[[string]$record['id']] = $record
}

$matches = foreach ($record in $latest.Values) {
    if ($record['status'] -eq 'expired' -or $record['status'] -eq 'superseded') { continue }
    if (-not $IncludeCandidates -and $record['status'] -ne 'active') { continue }
    if ($record['scope'] -eq 'project' -and $record['project_id'] -ne $ProjectId) { continue }
    $reviewAt = [DateTime]::MinValue
    if ([DateTime]::TryParse([string]$record['review_at'], [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind, [ref]$reviewAt) -and $reviewAt.ToUniversalTime() -lt (Get-Date).ToUniversalTime()) { continue }
    $text = (([string]$record['trigger']) + ' ' + [string]$record['action'] + ' ' + (@($record['evidence']) -join ' ')).ToLowerInvariant()
    $hits = @($terms | Where-Object { $text.Contains($_) }).Count
    if ($hits -eq 0) { continue }
    [PSCustomObject]@{
        score = ($hits * 10) + ([double]$record['confidence'] * 5) + $(if ($record['status'] -eq 'active') { 2 } else { 0 })
        record = $record
    }
}

$matches | Sort-Object -Property score -Descending | Select-Object -First $Limit | ForEach-Object {
    [ordered]@{ score = $_.score; record = $_.record } | ConvertTo-Json -Compress -Depth 8
}
