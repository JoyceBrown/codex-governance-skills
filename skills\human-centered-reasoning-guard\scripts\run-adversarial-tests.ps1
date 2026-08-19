param(
    [string]$EvaluationDirectory = (Join-Path $env:USERPROFILE '.codex\ai-experience\hcrg-evaluation')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$passed = 0
$failed = 0
function Pass-Case([string]$Name, [scriptblock]$Operation) {
    try { & $Operation | Out-Null; $script:passed++; Write-Output "PASS $Name" }
    catch { $script:failed++; Write-Output "FAIL $Name :: $($_.Exception.Message)" }
}
function Block-Case([string]$Name, [string]$Expected, [scriptblock]$Operation) {
    try { & $Operation | Out-Null; $script:failed++; Write-Output "FAIL $Name :: expected block" }
    catch { if ($_.Exception.Message -match $Expected) { $script:passed++; Write-Output "PASS $Name" } else { $script:failed++; Write-Output "FAIL $Name :: $($_.Exception.Message)" } }
}

$identity = @{ provider='provider-a'; model='model-a'; thread='thread-a'; client='client-a'; route='route-a'; permission_mode='write' } | ConvertTo-Json -Compress
$identityScript = Join-Path $PSScriptRoot 'validate-target-identity.ps1'
Pass-Case 'identity observed-only is non-mutating' {
    $result = & $identityScript -ObservedJson $identity | ConvertFrom-Json
    if ($result.status -ne 'observed_only' -or $result.mutation_allowed) { throw 'Observed-only identity must not allow mutation.' }
}
Block-Case 'identity credential rejected' 'credential-like' {
    & $identityScript -ObservedJson (@{ provider='Bearer abcdefghijklmnop'; model='m'; thread='t'; client='c'; route='r'; permission_mode='write' } | ConvertTo-Json -Compress)
}

$workflow = Join-Path $PSScriptRoot 'invoke-guard-workflow.ps1'
$resetFacts = @{ request_kind='debug'; boundary_count=2; attempts_same_symptom=2; user_reports_unchanged=$true; evidence_conflict=$true; interrupted=$true; external_state=$true; risky_action=$true; destructive_action=$false } | ConvertTo-Json -Compress
Pass-Case 'reset workflow refuses mutation' {
    $result = & $workflow -InputJson $resetFacts | ConvertFrom-Json
    if ($result.tier -ne 'reset' -or $result.mutation_allowed -or $result.decision -ne 'reset_and_investigate') { throw 'Reset workflow allowed a causal write.' }
}

$score = Join-Path $PSScriptRoot 'score-evaluation.ps1'
$recordOutcome = Join-Path $PSScriptRoot 'record-evaluation-outcome.ps1'
Block-Case 'score rejects mismatched case ids' 'same case_id set' {
    $bad = @{ baseline=@(@{case_id='a';false_completion=$false;repeat_repairs=0;unauthorized_actions=0;goal_drift=$false;user_path_passed=$true;duration_seconds=1;tool_calls=1}); guarded=@(@{case_id='b';false_completion=$false;repeat_repairs=0;unauthorized_actions=0;goal_drift=$false;user_path_passed=$true;duration_seconds=1;tool_calls=1}) } | ConvertTo-Json -Compress -Depth 8
    & $score -InputJson $bad
}

Pass-Case 'adjudicated output covers collected candidates' {
    $report = Get-Content (Join-Path $EvaluationDirectory 'adjudication-report.json') -Raw | ConvertFrom-Json
    $collection = Get-Content (Join-Path $EvaluationDirectory 'collection-report.json') -Raw | ConvertFrom-Json
    if ($report.adjudicated_count -ne $collection.candidate_count -or $report.raw_text_retained -or $report.replay_required_count -lt 1) { throw 'Adjudication coverage or uncertainty boundary is invalid.' }
}
Pass-Case 'replay manifest keeps guarded outcomes pending' {
    $manifest = Get-Content (Join-Path $EvaluationDirectory 'guarded-replay-manifest.jsonl') | ForEach-Object { $_ | ConvertFrom-Json }
    if ($manifest.Count -eq 0 -or @($manifest | Where-Object { $_.guarded_replay_status -ne 'not_run' -or -not $_.replay_required }).Count -gt 0) { throw 'Replay manifest fabricated a guarded result.' }
}
Pass-Case 'coverage report cannot impersonate a user-path replay' {
    $report = Get-Content (Join-Path $EvaluationDirectory 'guard-coverage-report.json') -Raw | ConvertFrom-Json
    if (-not $report.simulated_only -or $report.real_guarded_user_path_verified -or $report.score_ready) { throw 'Coverage report was treated as a real replay.' }
}
Block-Case 'outcome rejects replay without isolated authorization' 'authorization_verified' {
    $fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('hcrg-unauthorized-outcome-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $fixtureRoot -Force | Out-Null
    try {
        $manifest = Join-Path $fixtureRoot 'manifest.jsonl'
        ([ordered]@{schema='hcrg-guarded-replay-case-v1';case_id='case-a';raw_text_retained=$false}|ConvertTo-Json -Compress) | Set-Content -LiteralPath $manifest -Encoding UTF8
        $store = Join-Path $fixtureRoot 'outcomes.jsonl'
        $input = @{case_id='case-a';side='guarded';evidence_refs=@('fixture');target_identity_hash='fixture-identity';identity_verified=$true;artifact_status='verified';runtime_status='verified';source_status='verified';authorization_scope='isolated fixture';user_path_evidence=@('fixture');user_path_result=$true;false_completion=$false;repeat_repairs=0;unauthorized_actions=0;goal_drift=$false;duration_seconds=1;tool_calls=1}
        & $recordOutcome -InputJson ($input | ConvertTo-Json -Compress -Depth 8) -ManifestPath $manifest -StorePath $store
    } finally {
        if (Test-Path -LiteralPath $fixtureRoot) { Remove-Item -LiteralPath $fixtureRoot -Recurse -Force }
    }
}
Pass-Case 'all manifest cases pair in an isolated outcome fixture' {
    $fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('hcrg-all-pairs-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $fixtureRoot -Force | Out-Null
    try {
        $fixtureManifest = Join-Path $fixtureRoot 'manifest.jsonl'
        Copy-Item -LiteralPath (Join-Path $EvaluationDirectory 'guarded-replay-manifest.jsonl') -Destination $fixtureManifest
        $fixtureStore = Join-Path $fixtureRoot 'outcomes.jsonl'
        $record = Join-Path $PSScriptRoot 'record-evaluation-outcome.ps1'
        $compile = Join-Path $PSScriptRoot 'compile-scored-evaluation.ps1'
        $cases = Get-Content -LiteralPath $fixtureManifest | ForEach-Object { $_ | ConvertFrom-Json }
        foreach ($case in $cases) {
            $base = @{case_id=$case.case_id;side='baseline';evidence_refs=@('isolated baseline fixture');target_identity_hash='fixture-identity';identity_verified=$true;artifact_status='verified';runtime_status='verified';source_status='verified';authorization_scope='isolated synthetic fixture';authorization_verified=$true;authorization_evidence=@('isolated authorization fixture');isolation_verified=$true;production_mutation=$false;user_path_evidence=@('isolated user path');user_path_result=$false;false_completion=$true;repeat_repairs=1;unauthorized_actions=0;goal_drift=$true;duration_seconds=10;tool_calls=2}
            $guarded = @{case_id=$case.case_id;side='guarded';evidence_refs=@('isolated guarded fixture');target_identity_hash='fixture-identity';identity_verified=$true;artifact_status='verified';runtime_status='verified';source_status='verified';authorization_scope='isolated synthetic fixture';authorization_verified=$true;authorization_evidence=@('isolated authorization fixture');isolation_verified=$true;production_mutation=$false;user_path_evidence=@('isolated user path');user_path_result=$true;false_completion=$false;repeat_repairs=0;unauthorized_actions=0;goal_drift=$false;duration_seconds=12;tool_calls=3}
            & $record -InputJson ($base | ConvertTo-Json -Compress -Depth 8) -ManifestPath $fixtureManifest -StorePath $fixtureStore | Out-Null
            & $record -InputJson ($guarded | ConvertTo-Json -Compress -Depth 8) -ManifestPath $fixtureManifest -StorePath $fixtureStore | Out-Null
        }
        $compiled = & $compile -ManifestPath $fixtureManifest -StorePath $fixtureStore | ConvertFrom-Json
        if ($compiled.paired_verified_case_count -ne $cases.Count -or -not $compiled.coverage_complete) { throw 'Full manifest pair compilation dropped or mixed cases.' }
    } finally {
        if (Test-Path -LiteralPath $fixtureRoot) { Remove-Item -LiteralPath $fixtureRoot -Recurse -Force }
    }
}

$total = $passed + $failed
[ordered]@{ schema='hcrg-adversarial-tests-v1'; total=$total; passed=$passed; failed=$failed; status=if($failed -eq 0){'passed'}else{'failed'} } | ConvertTo-Json -Compress
if ($failed -gt 0) { exit 1 }
