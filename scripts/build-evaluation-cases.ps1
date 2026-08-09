param(
    [string]$CandidatesPath = (Join-Path $env:USERPROFILE '.codex\ai-experience\hcrg-evaluation\candidates.jsonl'),
    [string]$OutputDirectory = (Join-Path $env:USERPROFILE '.codex\ai-experience\hcrg-evaluation'),
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $CandidatesPath -PathType Leaf)) { throw "CandidatesPath does not exist: $CandidatesPath" }

function Get-Hash([string]$Value) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return (($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)) | ForEach-Object { $_.ToString('x2') }) -join '').Substring(0, 20)
    } finally { $sha.Dispose() }
}

function Read-Candidates([string]$Path) {
    $items = @()
    $seen = @{}
    foreach ($line in [IO.File]::ReadLines((Resolve-Path -LiteralPath $Path))) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($line -match '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})') { throw 'Credential-like value detected in candidate input.' }
        try { $item = $line | ConvertFrom-Json } catch { throw 'CandidatesPath contains invalid JSON.' }
        if ($null -eq $item -or $item -is [array]) { throw 'Each candidate line must contain one object.' }
        foreach ($field in @('case_id', 'status', 'priority', 'thread_hash', 'source_kinds', 'signal_categories', 'classification_hits', 'confidence', 'raw_text_retained')) {
            if (-not ($item.PSObject.Properties.Name -contains $field)) { throw "Candidate is missing '$field'." }
        }
        $caseId = [string]$item.case_id
        if ([string]::IsNullOrWhiteSpace($caseId) -or $seen.ContainsKey($caseId)) { throw "Duplicate or empty candidate case_id: $caseId" }
        if ([bool]$item.raw_text_retained) { throw "Candidate '$caseId' retains raw text; refusing to evaluate." }
        $seen[$caseId] = $true
        $items += $item
    }
    if ($items.Count -eq 0) { throw 'No candidates found.' }
    return ,$items
}

function Get-Hints([object]$Candidate) {
    $signals = @($Candidate.signal_categories | ForEach-Object { [string]$_ })
    $direct = @()
    if ($signals -contains 'unchanged_user_result' -or $signals -contains 'completion_disputed') { $direct += 'false_completion' }
    if ($signals -contains 'plan_or_goal_change') { $direct += 'goal_drift' }
    if ($signals -contains 'authorization_or_destructive_scope') { $direct += 'unauthorized_actions' }
    if ($signals -contains 'unchanged_user_result' -and $signals -contains 'interrupted_or_crashed') { $direct += 'repeat_repairs' }
    $coverage = @($Candidate.source_kinds | ForEach-Object { [string]$_ } | Sort-Object -Unique)
    $coverageClass = if ($coverage.Count -gt 1) { 'multi_source' } elseif ($coverage -contains 'session_list') { 'session_list_only' } elseif ($coverage -contains 'archived') { 'archived_only' } else { 'local_only' }
    [ordered]@{
        false_completion = [bool]($direct -contains 'false_completion')
        goal_drift = [bool]($direct -contains 'goal_drift')
        repeat_repairs = [bool]($direct -contains 'repeat_repairs')
        unauthorized_actions = [bool]($direct -contains 'unauthorized_actions')
        user_path_passed = $null
        hint_basis = @($direct | Sort-Object -Unique)
        hint_is_not_verdict = $true
        source_coverage = $coverageClass
    }
}

function Get-GroupKey([object]$Hints) {
    $keys = @(@('false_completion', 'goal_drift', 'repeat_repairs', 'unauthorized_actions') | Where-Object { [bool]$Hints.$_ })
    if ($keys.Count -eq 0) { return 'unclassified_signal' }
    return ($keys -join '+')
}

$candidates = Read-Candidates $CandidatesPath
$queue = @()
$groups = @{}
foreach ($candidate in $candidates) {
    $hints = Get-Hints $candidate
    $groupKey = Get-GroupKey $hints
    $groupId = 'group-' + (Get-Hash $groupKey)
    if (-not $groups.ContainsKey($groupId)) {
        $groups[$groupId] = [ordered]@{
            group_id = $groupId
            group_key = $groupKey
            candidate_count = 0
            case_ids = New-Object 'System.Collections.Generic.List[string]'
            source_coverage = New-Object 'System.Collections.Generic.HashSet[string]'
            review_status = 'needs_manual_review'
        }
    }
    $group = $groups[$groupId]
    $group.candidate_count = [int]$group.candidate_count + 1
    [void]$group.case_ids.Add([string]$candidate.case_id)
    [void]$group.source_coverage.Add([string]$hints.source_coverage)
    $queue += [ordered]@{
        schema = 'hcrg-evaluation-review-case-v1'
        case_id = [string]$candidate.case_id
        status = 'needs_manual_review'
        priority = [string]$candidate.priority
        thread_hash = [string]$candidate.thread_hash
        source_kinds = @($candidate.source_kinds | ForEach-Object { [string]$_ } | Sort-Object -Unique)
        signal_categories = @($candidate.signal_categories | ForEach-Object { [string]$_ } | Sort-Object -Unique)
        classification_hits = [int]$candidate.classification_hits
        confidence = [double]$candidate.confidence
        hint_dimensions = $hints
        group_id = $groupId
        review_notes = @('Keyword/category discovery only.', 'Confirm outcome from an authorized replay or manually reviewed evidence before scoring or memory promotion.')
        raw_text_retained = $false
    }
}

$paired = @($queue | ForEach-Object {
    [ordered]@{
        case_id = $_.case_id
        review_status = 'needs_manual_review'
        evidence_ref = $null
        baseline = [ordered]@{ false_completion = $null; repeat_repairs = $null; unauthorized_actions = $null; goal_drift = $null; user_path_passed = $null; duration_seconds = $null; tool_calls = $null }
        guarded = [ordered]@{ false_completion = $null; repeat_repairs = $null; unauthorized_actions = $null; goal_drift = $null; user_path_passed = $null; duration_seconds = $null; tool_calls = $null }
    }
})
$report = [ordered]@{
    schema = 'hcrg-evaluation-case-build-report-v1'
    built_at = (Get-Date).ToUniversalTime().ToString('o')
    input = [IO.Path]::GetFileName($CandidatesPath)
    candidate_count = $queue.Count
    group_count = $groups.Count
    review_case_count = @($paired).Count
    review_status = 'needs_manual_review'
    score_ready = $false
    raw_text_retained = $false
    credential_like_values = 0
    groups = @($groups.Values | ForEach-Object {
        [ordered]@{
            group_id = $_.group_id
            group_key = $_.group_key
            candidate_count = $_.candidate_count
            case_ids = @($_.case_ids)
            source_coverage = @($_.source_coverage | Sort-Object)
            review_status = $_.review_status
        }
    } | Sort-Object group_key)
}

if (-not $DryRun) {
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    $queuePath = Join-Path $OutputDirectory 'review-queue.jsonl'
    $templatePath = Join-Path $OutputDirectory 'evaluation-input-template.json'
    $reportPath = Join-Path $OutputDirectory 'case-build-report.json'
    $tmpQueue = "$queuePath.$([guid]::NewGuid().ToString('N')).tmp"
    try {
        $writer = New-Object IO.StreamWriter($tmpQueue, $false, (New-Object Text.UTF8Encoding($false)))
        try { foreach ($item in $queue) { $writer.WriteLine(($item | ConvertTo-Json -Compress -Depth 12)) } } finally { $writer.Dispose() }
        Move-Item -LiteralPath $tmpQueue -Destination $queuePath -Force
        [ordered]@{ schema = 'hcrg-evaluation-input-template-v1'; review_status = 'needs_manual_review'; score_ready = $false; cases = $paired; instructions = @('Fill only from reviewed, authorized evidence or replay.', 'Keep baseline and guarded case_id sets identical.', 'Run score-evaluation.ps1 only after every metric is non-null and verified.', 'Do not copy raw conversation text, paths, attachments, credentials, cookies, tokens, or prompts.') } | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $templatePath -Encoding UTF8
        $report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    } finally { if (Test-Path -LiteralPath $tmpQueue) { Remove-Item -LiteralPath $tmpQueue -Force } }
}

$report | ConvertTo-Json -Depth 12
