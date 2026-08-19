param(
    [string]$EvaluationDirectory = (Join-Path $env:USERPROFILE '.codex\ai-experience\hcrg-evaluation')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$required = @('candidates.jsonl','review-queue.jsonl','adjudicated-cases.jsonl','guarded-replay-manifest.jsonl','guard-coverage.jsonl')
foreach ($name in $required) { if (-not (Test-Path -LiteralPath (Join-Path $EvaluationDirectory $name) -PathType Leaf)) { throw "Missing evaluation artifact: $name" } }
function Read-JsonlIds([string]$Path, [string]$RequiredSchema) {
    $ids = @{}
    $count = 0
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($line -match '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})') { throw "Credential-like value detected in $([IO.Path]::GetFileName($Path))." }
        $item = $line | ConvertFrom-Json
        if ([string]$item.schema -ne $RequiredSchema) { throw "Unexpected schema in $([IO.Path]::GetFileName($Path))." }
        if ([bool]$item.raw_text_retained) { throw "Raw text retention flag in $([IO.Path]::GetFileName($Path))." }
        $id = [string]$item.case_id
        if ([string]::IsNullOrWhiteSpace($id) -or $ids.ContainsKey($id)) { throw "Duplicate or empty case_id in $([IO.Path]::GetFileName($Path))." }
        $ids[$id] = $true; $count++
    }
    return [ordered]@{ids=$ids;count=$count}
}
$candidates = Read-JsonlIds (Join-Path $EvaluationDirectory 'candidates.jsonl') 'hcrg-evaluation-candidate-v1'
$queue = Read-JsonlIds (Join-Path $EvaluationDirectory 'review-queue.jsonl') 'hcrg-evaluation-review-case-v1'
$adjudicated = Read-JsonlIds (Join-Path $EvaluationDirectory 'adjudicated-cases.jsonl') 'hcrg-evaluation-adjudicated-case-v1'
$replay = Read-JsonlIds (Join-Path $EvaluationDirectory 'guarded-replay-manifest.jsonl') 'hcrg-guarded-replay-case-v1'
$coverage = Read-JsonlIds (Join-Path $EvaluationDirectory 'guard-coverage.jsonl') 'hcrg-guard-coverage-case-v1'
$baseline = @($candidates.ids.Keys | Sort-Object) -join "`n"
foreach ($named in @(@{name='review queue';data=$queue},@{name='adjudication';data=$adjudicated},@{name='replay manifest';data=$replay},@{name='guard coverage';data=$coverage})) {
    if ((@($named.data.ids.Keys | Sort-Object) -join "`n") -ne $baseline) { throw "Case ID set diverged in $($named.name)." }
}
[ordered]@{ schema='hcrg-evaluation-artifacts-validation-v1'; case_count=$candidates.count; all_case_sets_match=$true; raw_text_retained=$false; credential_like_values=0; score_ready=$false } | ConvertTo-Json -Compress
