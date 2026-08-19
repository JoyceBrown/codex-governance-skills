param(
    [string[]]$SourcePaths,
    [string]$OutputPath = (Join-Path $env:USERPROFILE '.codex\ai-experience\hcrg-evaluation\candidates.jsonl'),
    [Int64]$MaxBytes = 1610612736,
    [int]$MaxFiles = 512,
    [int]$MaxLineChars = 1048576,
    [switch]$IncludeBackups,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($MaxBytes -lt 1048576) { throw 'MaxBytes must be at least 1048576.' }
if ($MaxFiles -lt 1 -or $MaxFiles -gt 4096) { throw 'MaxFiles must be between 1 and 4096.' }
if ($MaxLineChars -lt 1024 -or $MaxLineChars -gt 8388608) { throw 'MaxLineChars must be between 1024 and 8388608.' }

function Get-Hash([string]$Value) {
    $bytes = [Text.Encoding]::UTF8.GetBytes($Value)
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return (($hash.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) -join '').Substring(0, 20) } finally { $hash.Dispose() }
}

function Get-SourceKind([string]$Path) {
    $value = $Path.ToLowerInvariant()
    if ($value.EndsWith('session_index.jsonl')) { return 'session_list' }
    if ($value -match '\\archived_sessions\\') { return 'archived' }
    if ($value -match '\\backups\\') { return 'backup' }
    return 'local'
}

function Get-ThreadSeed([string]$Line, [string]$Path) {
    $pathMatch = [regex]::Match($Path, '(?i)([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})')
    if ($pathMatch.Success) { return $pathMatch.Groups[1].Value.ToLowerInvariant() }
    $lineMatch = [regex]::Match($Line, '(?i)"(?:thread_id|session_id|id)"\s*:\s*"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"')
    if ($lineMatch.Success) { return $lineMatch.Groups[1].Value.ToLowerInvariant() }
    return 'unknown:' + (Get-Hash([IO.Path]::GetFileName($Path)))
}

function Get-ObservedAt([string]$Line) {
    $match = [regex]::Match($Line, '"(?:timestamp|updated_at|created_at)"\s*:\s*"([^"\\]{8,64})"')
    if ($match.Success) { return $match.Groups[1].Value }
    return ''
}

function Is-UserFacingLine([string]$Line) {
    return $Line -match '(?i)"role"\s*:\s*"user"' -or $Line -match '(?i)"thread_name"\s*:' -or $Line -match '(?i)\[\d+\]\s*user\s*:'
}

$patterns = [ordered]@{
    unchanged_user_result = '(?i)(no\s+(?:change|response)|still\s+(?:not|cannot|fail)|not\s+(?:working|work|fixed)|\u6ca1\u53d8|\u8fd8\u662f|\u4e0d\u884c|\u65e0\u6548|\u6ca1\u53cd\u5e94)'
    sync_or_identity_drift = '(?i)(synchroni[sz]|\bsync\b|provider|thread|session\s+list|cache|stale|route|\u540c\u6b65|\u4f1a\u8bdd|\u7ebf\u7a0b|\u7f13\u5b58|\u8def\u7531|\u670d\u52a1\u5546)'
    availability_or_latency = '(?i)(timeout|offline|cannot\s+open|connection\s+(?:failed|timeout)|slow|loading|\u8fde\u4e0d\u4e0a|\u6253\u4e0d\u5f00|\u8d85\u65f6|\u52a0\u8f7d\u592a\u6162|\u79bb\u7ebf)'
    interrupted_or_crashed = '(?i)(interrupted|stopped|crash|resume|\u4e2d\u65ad|\u6682\u505c|\u5d29\u6e83|\u7ee7\u7eed)'
    plan_or_goal_change = '(?i)(roadmap|plan|requirement|goal|scope|pivot|\u8ba1\u5212|\u8def\u7ebf|\u8bc9\u6c42|\u76ee\u6807|\u8303\u56f4|\u65b9\u5411)'
    authorization_or_destructive_scope = '(?i)(permission|authori[sz]|delete|remove|archive|migrate|\u6388\u6743|\u5220\u9664|\u5f52\u6863|\u8fc1\u79fb|\u6743\u9650)'
    ui_interaction_failure = '(?i)(click|touch|scroll|keyboard|input\s+box|gesture|\u70b9\u51fb|\u89e6\u5c4f|\u6ed1\u52a8|\u952e\u76d8|\u8f93\u5165\u6846|\u624b\u52bf)'
    completion_disputed = '(?i)(not\s+(?:done|complete|finished)|unfinished|\u6ca1\u5b8c\u6210|\u6ca1\u89e3\u51b3|\u6ca1\u5904\u7406\u597d)'
}

if ($null -eq $SourcePaths -or $SourcePaths.Count -eq 0) {
    $SourcePaths = @(
        (Join-Path $env:USERPROFILE '.codex\session_index.jsonl'),
        (Join-Path $env:USERPROFILE '.codex\archived_sessions'),
        (Join-Path $env:USERPROFILE '.codex\sessions')
    )
    if ($IncludeBackups) { $SourcePaths += (Join-Path $env:USERPROFILE '.codex\backups\session-unique') }
}

$files = @()
foreach ($source in $SourcePaths) {
    if (-not (Test-Path -LiteralPath $source)) { continue }
    $item = Get-Item -LiteralPath $source
    if ($item.PSIsContainer) {
        $files += Get-ChildItem -LiteralPath $item.FullName -File -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Extension -eq '.jsonl' }
    } elseif ($item.Extension -eq '.jsonl') {
        $files += $item
    }
}
$files = @($files | Sort-Object FullName -Unique | Select-Object -First $MaxFiles)

$aggregates = @{}
$scannedFiles = 0
[Int64]$scannedBytes = 0
[Int64]$scannedLines = 0
[Int64]$eligibleLines = 0
[Int64]$matchedLines = 0
[Int64]$skippedLongLines = 0
$skippedFiles = 0

foreach ($file in $files) {
    if ($scannedBytes + [Int64]$file.Length -gt $MaxBytes) { $skippedFiles += 1; continue }
    $scannedFiles += 1
    $scannedBytes += [Int64]$file.Length
    $sourceKind = Get-SourceKind $file.FullName
    try { $reader = New-Object IO.StreamReader($file.FullName, $true) } catch { $skippedFiles += 1; continue }
    try {
        while (($line = $reader.ReadLine()) -ne $null) {
            $scannedLines += 1
            if ($line.Length -gt $MaxLineChars) { $skippedLongLines += 1; continue }
            if (-not (Is-UserFacingLine $line)) { continue }
            $eligibleLines += 1
            $categories = @()
            foreach ($entry in $patterns.GetEnumerator()) { if ($line -match $entry.Value) { $categories += $entry.Key } }
            if ($categories.Count -eq 0) { continue }
            $matchedLines += 1
            $threadHash = Get-Hash (Get-ThreadSeed $line $file.FullName)
            if (-not $aggregates.ContainsKey($threadHash)) {
                $aggregates[$threadHash] = [ordered]@{
                    thread_hash = $threadHash
                    source_kinds = New-Object 'System.Collections.Generic.HashSet[string]'
                    categories = New-Object 'System.Collections.Generic.HashSet[string]'
                    first_observed_at = ''
                    last_observed_at = ''
                    classification_hits = 0
                }
            }
            $aggregate = $aggregates[$threadHash]
            [void]$aggregate.source_kinds.Add($sourceKind)
            foreach ($category in $categories) { [void]$aggregate.categories.Add($category) }
            $aggregate.classification_hits = [int]$aggregate.classification_hits + 1
            $observedAt = Get-ObservedAt $line
            if ($observedAt) {
                if (-not $aggregate.first_observed_at -or $observedAt -lt $aggregate.first_observed_at) { $aggregate.first_observed_at = $observedAt }
                if (-not $aggregate.last_observed_at -or $observedAt -gt $aggregate.last_observed_at) { $aggregate.last_observed_at = $observedAt }
            }
        }
    } finally {
        $reader.Dispose()
    }
}

$candidates = foreach ($aggregate in $aggregates.Values) {
    $categories = @($aggregate.categories | Sort-Object)
    $hasPrimaryEvidence = @($aggregate.source_kinds | Where-Object { $_ -in @('archived', 'local') }).Count -gt 0
    $indexOnly = @($aggregate.source_kinds).Count -eq 1 -and @($aggregate.source_kinds | Where-Object { $_ -eq 'session_list' }).Count -eq 1
    $hasDirectFailure = @($categories | Where-Object { $_ -in @('unchanged_user_result', 'completion_disputed') }).Count -gt 0
    $hasBoundaryFailure = @($categories | Where-Object { $_ -in @('sync_or_identity_drift', 'availability_or_latency', 'interrupted_or_crashed') }).Count -ge 2
    $priority = if ($hasPrimaryEvidence -and ($hasDirectFailure -or $hasBoundaryFailure)) { 'P0' } else { 'P1' }
    $confidence = if ($indexOnly) { 0.1 } elseif ($aggregate.classification_hits -ge 3 -and $categories.Count -ge 2) { 0.5 } elseif ($categories.Count -ge 2) { 0.35 } else { 0.2 }
    [ordered]@{
        schema = 'hcrg-evaluation-candidate-v1'
        case_id = 'candidate-' + $aggregate.thread_hash
        status = 'candidate'
        priority = $priority
        thread_hash = $aggregate.thread_hash
        source_kinds = @($aggregate.source_kinds | Sort-Object)
        signal_categories = $categories
        classification_hits = $aggregate.classification_hits
        confidence = $confidence
        first_observed_at = $aggregate.first_observed_at
        last_observed_at = $aggregate.last_observed_at
        raw_text_retained = $false
    }
}
$candidates = @($candidates | Sort-Object @{Expression = { if ($_.priority -eq 'P0') { 0 } else { 1 } }}, @{Expression = 'classification_hits'; Descending = $true})
$summary = [ordered]@{
    schema = 'hcrg-evaluation-collection-report-v1'
    collected_at = (Get-Date).ToUniversalTime().ToString('o')
    sources = @('session_list', 'archived', 'local') + $(if ($IncludeBackups) { @('backup') } else { @() })
    scanned_files = $scannedFiles
    skipped_files = $skippedFiles
    scanned_bytes = $scannedBytes
    scanned_lines = $scannedLines
    eligible_user_lines = $eligibleLines
    matched_lines = $matchedLines
    skipped_long_lines = $skippedLongLines
    candidate_count = $candidates.Count
    raw_text_retained = $false
    output_written = (-not $DryRun)
}

if (-not $DryRun) {
    $parent = Split-Path -Parent $OutputPath
    if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $tempPath = "$OutputPath.$([guid]::NewGuid().ToString('N')).tmp"
    try {
        $encoding = New-Object Text.UTF8Encoding($false)
        $writer = New-Object IO.StreamWriter($tempPath, $false, $encoding)
        try {
            foreach ($candidate in $candidates) {
                $line = $candidate | ConvertTo-Json -Compress -Depth 8
                if ($line -match '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})') { throw 'Refusing to write credential-like candidate output.' }
                $writer.WriteLine($line)
            }
        } finally { $writer.Dispose() }
        Move-Item -LiteralPath $tempPath -Destination $OutputPath -Force
        ($summary | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath (Join-Path $parent 'collection-report.json') -Encoding UTF8
    } finally {
        if (Test-Path -LiteralPath $tempPath) { [IO.File]::Delete($tempPath) }
    }
}

$summary | ConvertTo-Json -Depth 8
