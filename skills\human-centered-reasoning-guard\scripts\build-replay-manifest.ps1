param(
    [string]$AdjudicatedPath = (Join-Path $env:USERPROFILE '.codex\ai-experience\hcrg-evaluation\adjudicated-cases.jsonl'),
    [string]$OutputDirectory = (Join-Path $env:USERPROFILE '.codex\ai-experience\hcrg-evaluation'),
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $AdjudicatedPath -PathType Leaf)) { throw "AdjudicatedPath does not exist: $AdjudicatedPath" }
$cases = @()
$seen = @{}
foreach ($line in [IO.File]::ReadLines((Resolve-Path -LiteralPath $AdjudicatedPath))) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    if ($line -match '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})') { throw 'Credential-like value detected in adjudication input.' }
    $case = $line | ConvertFrom-Json
    foreach ($field in @('case_id','adjudication_status','evidence_strength','labels','replay_required','raw_text_retained')) {
        if (-not ($case.PSObject.Properties.Name -contains $field)) { throw "Adjudicated case missing '$field'." }
    }
    if ([bool]$case.raw_text_retained) { throw "Case '$($case.case_id)' retains raw text." }
    if ($seen.ContainsKey([string]$case.case_id)) { throw "Duplicate case_id: $($case.case_id)" }
    $seen[[string]$case.case_id] = $true
    $cases += $case
}
if ($cases.Count -eq 0) { throw 'No adjudicated cases found.' }

$manifest = @($cases | ForEach-Object {
    $historical = [string]$_.adjudication_status
    $priority = if ($historical -eq 'confirmed_failure') { 'P0' } elseif ($historical -like 'inconclusive*') { 'P1' } else { 'P2' }
    [ordered]@{
        schema = 'hcrg-guarded-replay-case-v1'
        case_id = [string]$_.case_id
        priority = $priority
        historical_baseline_status = $historical
        baseline_labels = $_.labels
        baseline_evidence_strength = [string]$_.evidence_strength
        guarded_replay_status = 'not_run'
        guarded_result = $null
        acceptance_checks = @('same user-visible goal','same target identity','same source of truth','fresh user-path result','refresh or restart check when relevant')
        safety_constraints = @('no production mutation without explicit authorization','no new parallel human session','no unredacted transcript','one causal hypothesis per replay')
        replay_required = $true
        raw_text_retained = $false
    }
} | Sort-Object @{Expression={if($_.priority -eq 'P0'){0}elseif($_.priority -eq 'P1'){1}else{2}}}, case_id)
$report = [ordered]@{
    schema = 'hcrg-replay-manifest-report-v1'
    built_at = (Get-Date).ToUniversalTime().ToString('o')
    case_count = $manifest.Count
    historical_baseline_counts = @($manifest | Group-Object { [string]$_.historical_baseline_status } | ForEach-Object { [ordered]@{status=$_.Name;count=$_.Count} })
    guarded_replay_pending = $manifest.Count
    score_ready = $false
    raw_text_retained = $false
}
if (-not $DryRun) {
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    $manifestPath = Join-Path $OutputDirectory 'guarded-replay-manifest.jsonl'
    $reportPath = Join-Path $OutputDirectory 'replay-manifest-report.json'
    $tmp = "$manifestPath.$([guid]::NewGuid().ToString('N')).tmp"
    try {
        $writer = New-Object IO.StreamWriter($tmp, $false, (New-Object Text.UTF8Encoding($false)))
        try { foreach ($item in $manifest) { $writer.WriteLine(($item | ConvertTo-Json -Compress -Depth 10)) } } finally { $writer.Dispose() }
        Move-Item -LiteralPath $tmp -Destination $manifestPath -Force
        $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    } finally { if (Test-Path -LiteralPath $tmp) { [IO.File]::Delete($tmp) } }
}
$report | ConvertTo-Json -Depth 8
