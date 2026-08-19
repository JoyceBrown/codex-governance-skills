param(
    [string]$ManifestPath = (Join-Path $env:USERPROFILE '.codex\ai-experience\hcrg-evaluation\guarded-replay-manifest.jsonl'),
    [string]$StorePath = (Join-Path $env:USERPROFILE '.codex\ai-experience\hcrg-evaluation\verified-outcomes.jsonl')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { throw "ManifestPath does not exist: $ManifestPath" }
$manifest = @{}
foreach($line in Get-Content -LiteralPath $ManifestPath){if($line.Trim()){$item=$line|ConvertFrom-Json;$manifest[[string]$item.case_id]=$true}}
if($manifest.Count -eq 0){throw 'Replay manifest is empty.'}
$latest=@{}
if(Test-Path -LiteralPath $StorePath -PathType Leaf){
    foreach($line in Get-Content -LiteralPath $StorePath){
        if(-not $line.Trim()){continue}
        if($line -match '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})'){throw 'Credential-like value detected in outcome store.'}
        $item=$line|ConvertFrom-Json
        if([string]$item.schema -ne 'hcrg-evaluation-outcome-v2' -or [string]$item.verification_status -ne 'verified' -or [bool]$item.raw_text_retained){throw 'Outcome store contains an invalid or unverified record.'}
        if(-not [bool]$item.authorization_verified -or -not [bool]$item.isolation_verified -or [bool]$item.production_mutation -or [string]::IsNullOrWhiteSpace([string]$item.authorization_scope)){throw 'Outcome lacks verified isolated authorization evidence.'}
        if(-not $manifest.ContainsKey([string]$item.case_id)){throw 'Outcome references a case outside the manifest.'}
        $latest["$($item.case_id):$($item.side)"]=$item
    }
}
$baseline=@();$guarded=@();$pending=@()
foreach($caseId in $manifest.Keys|Sort-Object){
    $base=$latest["${caseId}:baseline"];$guard=$latest["${caseId}:guarded"]
    if($null -eq $base -or $null -eq $guard){$pending+=$caseId;continue}
    foreach($pair in @(@{side='baseline';item=$base},@{side='guarded';item=$guard})){
        foreach($field in @('false_completion','repeat_repairs','unauthorized_actions','goal_drift','user_path_passed','duration_seconds','tool_calls')){if(-not ($pair.item.PSObject.Properties.Name -contains $field)){throw "Missing metric '$field' in $($pair.side) outcome."}}
    }
    $baseline += [ordered]@{case_id=$caseId;false_completion=[bool]$base.false_completion;repeat_repairs=[int]$base.repeat_repairs;unauthorized_actions=[int]$base.unauthorized_actions;goal_drift=[bool]$base.goal_drift;user_path_passed=[bool]$base.user_path_passed;duration_seconds=[double]$base.duration_seconds;tool_calls=[int]$base.tool_calls}
    $guarded += [ordered]@{case_id=$caseId;false_completion=[bool]$guard.false_completion;repeat_repairs=[int]$guard.repeat_repairs;unauthorized_actions=[int]$guard.unauthorized_actions;goal_drift=[bool]$guard.goal_drift;user_path_passed=[bool]$guard.user_path_passed;duration_seconds=[double]$guard.duration_seconds;tool_calls=[int]$guard.tool_calls}
}
$score=$null
if($baseline.Count -gt 0){$score=& (Join-Path $PSScriptRoot 'score-evaluation.ps1') -InputJson (@{baseline=$baseline;guarded=$guarded}|ConvertTo-Json -Compress -Depth 12)|ConvertFrom-Json}
[ordered]@{schema='hcrg-scored-evaluation-compilation-v1';manifest_case_count=$manifest.Count;paired_verified_case_count=$baseline.Count;pending_case_count=$pending.Count;pending_case_ids=@($pending);score_ready=[bool]($baseline.Count -gt 0);coverage_complete=[bool]($pending.Count -eq 0);score=$score;real_user_path_verified=[bool]($baseline.Count -gt 0)}|ConvertTo-Json -Depth 12
