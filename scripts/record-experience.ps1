param(
    [Parameter(Mandatory = $true)]
    [string]$InputJson,
    [string]$StorePath = "$env:USERPROFILE\.codex\ai-experience\observations.jsonl"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$MaxInputBytes = 8192

function Fail([string]$Message) {
    throw $Message
}

if ([Text.Encoding]::UTF8.GetByteCount($InputJson) -gt $MaxInputBytes) {
    Fail "InputJson exceeds $MaxInputBytes bytes. Store an abstract summary, not a transcript."
}

try {
    $record = $InputJson | ConvertFrom-Json
} catch {
    Fail "InputJson must be valid JSON."
}

if ($null -eq $record -or $record -is [array]) { Fail "InputJson must contain one object." }

foreach ($field in @('trigger', 'action', 'scope', 'evidence')) {
    if (-not ($record.PSObject.Properties.Name -contains $field)) {
        Fail "Missing required field: $field"
    }
}

$trigger = [string]$record.trigger
$action = [string]$record.action
if ([string]::IsNullOrWhiteSpace($trigger) -or [string]::IsNullOrWhiteSpace($action)) {
    Fail "trigger and action must not be empty."
}

if ($record.scope -notin @('project', 'global')) {
    Fail "scope must be project or global."
}

$projectId = $null
if ($record.PSObject.Properties.Name -contains 'project_id' -and -not [string]::IsNullOrWhiteSpace([string]$record.project_id)) {
    $projectId = [string]$record.project_id
}
if ($record.scope -eq 'project' -and $null -eq $projectId) {
    Fail "project scope requires project_id."
}
if ($record.scope -eq 'global') { $projectId = $null }

$evidence = @($record.evidence | ForEach-Object { [string]$_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
if ($evidence.Count -eq 0) { Fail "evidence must contain at least one redacted item." }

$sensitiveField = '(?i)^(password|passwd|token|secret|cookie|authorization|bearer|api[_-]?key|private[_-]?key)$'
foreach ($property in $record.PSObject.Properties.Name) {
    if ($property -match $sensitiveField) {
        Fail "Input contains a sensitive field name; redact secrets before recording."
    }
}

$credentialPattern = '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})'
if ($InputJson -match $credentialPattern) {
    Fail "Input appears to contain a credential-like value; redact it before recording."
}

$parent = Split-Path -Parent $StorePath
if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }

$recordId = if ($record.PSObject.Properties.Name -contains 'id' -and -not [string]::IsNullOrWhiteSpace([string]$record.id)) {
    [string]$record.id
} else {
    [guid]::NewGuid().ToString('N')
}

$source = if ($record.PSObject.Properties.Name -contains 'source' -and -not [string]::IsNullOrWhiteSpace([string]$record.source)) {
    [string]$record.source
} else {
    'manual'
}

$output = [ordered]@{
    id = $recordId
    status = 'candidate'
    trigger = $trigger
    action = $action
    scope = [string]$record.scope
    project_id = $projectId
    source = $source
    evidence = $evidence
    confidence = 0.3
    counterexamples = @()
    supersedes = $null
    created_at = (Get-Date).ToUniversalTime().ToString('o')
    review_at = (Get-Date).ToUniversalTime().AddDays(30).ToString('o')
}

$line = $output | ConvertTo-Json -Compress -Depth 6
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
Write-Output "Recorded candidate experience: $($output.id)"
