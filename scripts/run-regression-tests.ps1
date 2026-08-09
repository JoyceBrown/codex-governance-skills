Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$passed = 0
$failed = 0

function Pass-Case([string]$Name, [scriptblock]$Operation) {
    try {
        & $Operation | Out-Null
        $script:passed += 1
        Write-Output "PASS $Name"
    } catch {
        $script:failed += 1
        Write-Output "FAIL $Name :: $($_.Exception.Message)"
    }
}

function Block-Case([string]$Name, [string]$Expected, [scriptblock]$Operation) {
    try {
        & $Operation | Out-Null
        throw 'Expected a block, but the operation passed.'
    } catch {
        if ($_.Exception.Message -match $Expected) {
            $script:passed += 1
            Write-Output "PASS $Name"
        } else {
            $script:failed += 1
            Write-Output "FAIL $Name :: $($_.Exception.Message)"
        }
    }
}

$factGate = Join-Path $PSScriptRoot 'fact-gate.ps1'
$goalGate = Join-Path $PSScriptRoot 'goal-integrity-gate.ps1'
$reconcile = Join-Path $PSScriptRoot 'reconcile-plan.ps1'
$drift = Join-Path $PSScriptRoot 'drift-report.ps1'
$receipt = Join-Path $PSScriptRoot 'validate-completion-receipt.ps1'
$score = Join-Path $PSScriptRoot 'score-evaluation.ps1'
$tier = Join-Path $PSScriptRoot 'classify-task-tier.ps1'
$identity = Join-Path $PSScriptRoot 'validate-target-identity.ps1'
$workflow = Join-Path $PSScriptRoot 'invoke-guard-workflow.ps1'
$memoryAudit = Join-Path $PSScriptRoot 'audit-experience-store.ps1'
$retrieveExperience = Join-Path $PSScriptRoot 'retrieve-experience.ps1'
$ledgerBridge = Join-Path $PSScriptRoot 'sync-durable-ledger.ps1'
$writeCard = Join-Path $PSScriptRoot 'write-task-card.ps1'
$recordOutcome = Join-Path $PSScriptRoot 'record-evaluation-outcome.ps1'
$compileOutcome = Join-Path $PSScriptRoot 'compile-scored-evaluation.ps1'

Pass-Case 'fact routine' {
    & $factGate -ActionType routine -FactsJson (@{ current_user_instruction = 'inspect'; purpose = 'collect baseline' } | ConvertTo-Json -Compress)
}
Block-Case 'fact missing baseline' 'missing baseline' {
    & $factGate -ActionType edit -FactsJson (@{ current_user_instruction = 'edit'; target_files = @('x'); callers_or_consumers = @('y'); public_surface = 'z'; source_of_truth = @('test') } | ConvertTo-Json -Compress)
}
Block-Case 'fact redacts credential pattern' 'Credential-like value' {
    & $factGate -ActionType routine -FactsJson (@{ current_user_instruction = 'Bearer abcdefghijklmnop'; purpose = 'test' } | ConvertTo-Json -Compress)
}

$inspectGoal = @{
    current_user_instruction = 'inspect a failed workflow'
    real_user_goal = 'the user sees one durable result'
    visible_success = 'the result is visible after refresh'
    proposed_action = 'compare authoritative record and client state'
    predicted_effect = 'identify the owning boundary'
    discriminating_check = 'compare one operation ID'
    expected_observation = 'one record exists or is absent'
    failure_signal = 'source and client disagree'
    baseline = @('user path fails')
    non_goals = @('deploy')
}
Pass-Case 'goal inspect' {
    & $goalGate -ActionType inspect -GoalJson ($inspectGoal | ConvertTo-Json -Compress)
}
$mutateGoal = $inspectGoal.Clone()
$mutateGoal.target = 'src/client.ts'
$mutateGoal.source_of_truth = @('integration test')
$mutateGoal.authorization = @('edit source')
$mutateGoal.rollback = 'revert diff'
Pass-Case 'goal mutate' {
    & $goalGate -ActionType mutate -GoalJson ($mutateGoal | ConvertTo-Json -Compress)
}
$completeGoal = @{
    current_user_instruction = 'complete task'
    real_user_goal = 'the user can finish the workflow'
    visible_success = 'user path passes'
    proposed_action = 'claim completion'
    predicted_effect = 'communicate verified result'
    evidence = @('fresh real-path check')
    user_path_result = 'pending'
    source_of_truth = @('authoritative source')
    baseline = @('previous failure')
    non_goals = @('new feature')
}
Block-Case 'goal completion requires user pass' 'user_path_result must be a verified pass' {
    & $goalGate -ActionType complete -GoalJson ($completeGoal | ConvertTo-Json -Compress)
}

$baseReconcile = @{
    task_id = 'test-task'
    current_plan_version = 'R1'
    current_goal = 'durable user result'
    new_instruction = 'add a cold-start acceptance check'
    goal_relation = 'refined'
    decision = 'integrate'
    rationale = 'goal remains the same'
    evidence = @('current user request')
    source_of_truth = @('user instruction')
    impact = 'one additional check'
    acceptance_delta = 'cold-start path must pass'
    authorization = @('change plan')
    next_action = 'update plan version'
}
Pass-Case 'reconcile integrate' {
    & $reconcile -InputJson ($baseReconcile | ConvertTo-Json -Compress)
}
$conflictReconcile = $baseReconcile.Clone()
$conflictReconcile.goal_relation = 'conflict'
$conflictReconcile.decision = 'supersede'
Block-Case 'reconcile conflict requires clarify' 'require clarify' {
    & $reconcile -InputJson ($conflictReconcile | ConvertTo-Json -Compress)
}
$clarifyReconcile = $baseReconcile.Clone()
$clarifyReconcile.goal_relation = 'conflict'
$clarifyReconcile.decision = 'clarify'
$clarifyReconcile.open_question = 'Which outcome should take priority?'
Pass-Case 'reconcile clarify' {
    & $reconcile -InputJson ($clarifyReconcile | ConvertTo-Json -Compress)
}

$baseDrift = @{
    task_id = 'test-task'
    plan_version = 'R1'
    target_version = 'build-1'
    goal_status = 'aligned'
    plan_status = 'current'
    artifact_status = 'matches_target'
    runtime_status = 'matches_target'
    identity_status = 'matches_target'
    source_status = 'authoritative'
    authorization_status = 'authorized'
    user_status = 'pass'
    evidence = @('fresh check')
}
Pass-Case 'drift level zero' {
    $result = & $drift -InputJson ($baseDrift | ConvertTo-Json -Compress) | ConvertFrom-Json
    if ($result.drift_level -ne 0 -or -not $result.completion_allowed) { throw 'Expected level 0 and completion allowed.' }
}
Pass-Case 'drift level one' {
    $input = $baseDrift.Clone(); $input.plan_status = 'stale'
    $result = & $drift -InputJson ($input | ConvertTo-Json -Compress) | ConvertFrom-Json
    if ($result.drift_level -ne 1 -or $result.recommendation -ne 'rebaseline_before_write') { throw 'Expected level 1 rebaseline.' }
}
Pass-Case 'drift level two' {
    $input = $baseDrift.Clone(); $input.user_status = 'fail'
    $result = & $drift -InputJson ($input | ConvertTo-Json -Compress) | ConvertFrom-Json
    if ($result.drift_level -ne 2 -or $result.recommendation -ne 'stop_current_patch_and_investigate_boundary') { throw 'Expected level 2 investigation.' }
}
Pass-Case 'drift level three identity mismatch' {
    $input = $baseDrift.Clone(); $input.identity_status = 'mismatch'
    $result = & $drift -InputJson ($input | ConvertTo-Json -Compress) | ConvertFrom-Json
    if ($result.drift_level -ne 3 -or $result.recommendation -ne 'block_mutation_and_clarify') { throw 'Expected level 3 block.' }
}

$baseReceipt = @{
    task_id = 'test-task'
    plan_version = 'R1'
    real_user_goal = 'durable user result'
    visible_success = 'user path passes'
    target_identity = @{ provider = 'test'; thread = 'thread-1'; client = 'desktop' }
    target_version = 'build-1'
    source_of_truth = @('authoritative source')
    artifact_evidence = @('fresh build check')
    runtime_evidence = @('fresh runtime check')
    user_path_evidence = @('fresh user path')
    identity_verified = $true
    artifact_status = 'verified'
    runtime_status = 'verified'
    source_status = 'verified'
    user_path_result = 'pass'
    drift_level = 0
    verified_at = '2026-08-09T12:00:00.0000000Z'
}
Pass-Case 'completion receipt' {
    $result = & $receipt -InputJson ($baseReceipt | ConvertTo-Json -Compress -Depth 8) | ConvertFrom-Json
    if (-not $result.completion_allowed -or [string]::IsNullOrWhiteSpace([string]$result.receipt_id)) { throw 'Expected valid receipt.' }
}
$receiptRaw = & $receipt -InputJson ($baseReceipt | ConvertTo-Json -Compress -Depth 8) | Out-String
$receiptObject = $receiptRaw | ConvertFrom-Json
$counterChecks = @(
    @{ kind = 'wrong_target_or_identity'; result = 'pass'; evidence_ref = 'check-1' },
    @{ kind = 'stale_artifact_or_runtime'; result = 'pass'; evidence_ref = 'check-2' },
    @{ kind = 'source_divergence_or_duplicate'; result = 'pass'; evidence_ref = 'check-3' },
    @{ kind = 'user_path_after_refresh'; result = 'pass'; evidence_ref = 'check-4' },
    @{ kind = 'rejected_path_no_false_success'; result = 'pass'; evidence_ref = 'check-5' }
)
$counterDrift = @{ schema = 'hcrg-drift-report-v1'; task_id = 'test-task'; plan_version = 'R1'; target_version = 'build-1'; drift_level = 0 }
Pass-Case 'counterfactual completion review' {
    $reviewInput = @{ task_id = 'test-task'; checks = $counterChecks } | ConvertTo-Json -Compress -Depth 8
    $driftInput = $counterDrift | ConvertTo-Json -Compress
    $review = & (Join-Path $PSScriptRoot 'review-completion-counterfactual.ps1') -ReceiptJson ($baseReceipt | ConvertTo-Json -Compress -Depth 8) -DriftJson $driftInput -ReviewJson $reviewInput | ConvertFrom-Json
    if (-not $review.review_passed -or [string]$review.receipt_id -ne [string]$receiptObject.receipt_id) { throw 'Expected matching counterfactual receipt.' }
}
Block-Case 'counterfactual requires all checks' 'Missing counterfactual check' {
    $reviewInput = @{ task_id = 'test-task'; checks = @($counterChecks | Select-Object -First 1) } | ConvertTo-Json -Compress -Depth 8
    & (Join-Path $PSScriptRoot 'review-completion-counterfactual.ps1') -ReceiptJson ($baseReceipt | ConvertTo-Json -Compress -Depth 8) -DriftJson ($counterDrift | ConvertTo-Json -Compress) -ReviewJson $reviewInput
}
Block-Case 'completion rejects drift' 'drift_level must be 0' {
    $input = $baseReceipt.Clone(); $input.drift_level = 2
    & $receipt -InputJson ($input | ConvertTo-Json -Compress -Depth 8)
}
Block-Case 'completion rejects unverified identity' 'identity_verified must be true' {
    $input = $baseReceipt.Clone(); $input.identity_verified = $false
    & $receipt -InputJson ($input | ConvertTo-Json -Compress -Depth 8)
}

$scoreInput = @{
    baseline = @(@{ case_id = 'case-1'; false_completion = $true; repeat_repairs = 1; unauthorized_actions = 0; goal_drift = $true; user_path_passed = $false; duration_seconds = 10; tool_calls = 3 })
    guarded = @(@{ case_id = 'case-1'; false_completion = $false; repeat_repairs = 0; unauthorized_actions = 0; goal_drift = $false; user_path_passed = $true; duration_seconds = 12; tool_calls = 4 })
}
Pass-Case 'evaluation includes goal drift' {
    $result = & $score -InputJson ($scoreInput | ConvertTo-Json -Compress -Depth 8) | ConvertFrom-Json
    if ($result.guarded.goal_drift_rate -ne 0 -or $result.guarded_minus_baseline.goal_drift_rate -ne -1) { throw 'Expected goal drift metric.' }
}

$builder = Join-Path $PSScriptRoot 'build-evaluation-cases.ps1'
Pass-Case 'evaluation case builder keeps review status and paired ids' {
    $fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('hcrg-builder-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $fixtureRoot -Force | Out-Null
    try {
        $candidatePath = Join-Path $fixtureRoot 'candidates.jsonl'
        $candidateLines = @(
            ([ordered]@{ schema='hcrg-evaluation-candidate-v1'; case_id='candidate-a'; status='candidate'; priority='P0'; thread_hash='hash-a'; source_kinds=@('local','archived'); signal_categories=@('unchanged_user_result','interrupted_or_crashed'); classification_hits=2; confidence=0.5; raw_text_retained=$false } | ConvertTo-Json -Compress),
            ([ordered]@{ schema='hcrg-evaluation-candidate-v1'; case_id='candidate-b'; status='candidate'; priority='P1'; thread_hash='hash-b'; source_kinds=@('session_list'); signal_categories=@('sync_or_identity_drift'); classification_hits=1; confidence=0.1; raw_text_retained=$false } | ConvertTo-Json -Compress)
        )
        $candidateLines | Set-Content -LiteralPath $candidatePath -Encoding UTF8
        $result = & $builder -CandidatesPath $candidatePath -OutputDirectory $fixtureRoot | ConvertFrom-Json
        if ($result.candidate_count -ne 2 -or $result.score_ready -or $result.review_status -ne 'needs_manual_review') { throw 'Builder did not preserve review-only status.' }
        $template = Get-Content (Join-Path $fixtureRoot 'evaluation-input-template.json') -Raw | ConvertFrom-Json
        $baseIds = @($template.cases | ForEach-Object case_id | Sort-Object)
        $guardedIds = @($template.cases | ForEach-Object case_id | Sort-Object)
        if (($baseIds -join "`n") -ne ($guardedIds -join "`n") -or $template.cases[0].baseline.user_path_passed -ne $null) { throw 'Builder template was not paired or left an unknown outcome.' }
    } finally {
        if (Test-Path -LiteralPath $fixtureRoot) { Remove-Item -LiteralPath $fixtureRoot -Recurse -Force }
    }
}

Pass-Case 'target identity requires expected match for mutation' {
    $observed = @{ provider='provider-a'; model='model-a'; thread='thread-a'; client='client-a'; route='route-a'; permission_mode='write' } | ConvertTo-Json -Compress
    $result = & $identity -ObservedJson $observed | ConvertFrom-Json
    if ($result.status -ne 'observed_only' -or $result.mutation_allowed) { throw 'Observed-only identity must remain non-mutating.' }
    $expected = @{ provider='provider-a'; model='model-a'; thread='thread-a'; client='client-a'; route='route-a'; permission_mode='write' } | ConvertTo-Json -Compress
    $matched = & $identity -ObservedJson $observed -ExpectedJson $expected | ConvertFrom-Json
    if ($matched.status -ne 'matched' -or -not $matched.mutation_allowed) { throw 'Matching identity was not accepted.' }
}
Pass-Case 'workflow reset redirects instead of writing' {
    $facts = @{ request_kind='debug'; boundary_count=2; attempts_same_symptom=2; user_reports_unchanged=$true; evidence_conflict=$true; interrupted=$true; external_state=$true; risky_action=$true; destructive_action=$false } | ConvertTo-Json -Compress
    $result = & $workflow -InputJson $facts | ConvertFrom-Json
    if ($result.tier -ne 'reset' -or $result.mutation_allowed -or $result.decision -ne 'reset_and_investigate') { throw 'Reset workflow did not redirect safely.' }
}
Pass-Case 'workflow full allows only matched identity and level-zero drift' {
    $fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('hcrg-workflow-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $fixtureRoot -Force | Out-Null
    try {
        $cardPath = Join-Path $fixtureRoot 'task-card.json'
        $card = @{ task_id='workflow-test'; plan_version='R1'; real_user_goal='verify one target'; visible_success='same target is verified'; authorization=@('inspect and make bounded change'); forbidden_actions=@('network mutation'); verified_facts=@('fixture'); unknowns=@('none'); target_identity=@{provider='provider-a';model='model-a';thread='thread-a';client='client-a';route='route-a';permission_mode='write'}; target_version='fixture-1'; source_of_truth=@('fixture'); baseline=@('fixture baseline'); attempts=0; next_action='inspect bounded target' }
        & $writeCard -InputJson ($card | ConvertTo-Json -Compress -Depth 8) -CardPath $cardPath | Out-Null
        $facts = @{ request_kind='debug'; boundary_count=2; attempts_same_symptom=0; user_reports_unchanged=$false; evidence_conflict=$false; interrupted=$false; external_state=$true; risky_action=$true; destructive_action=$false } | ConvertTo-Json -Compress
        $identityJson = @{provider='provider-a';model='model-a';thread='thread-a';client='client-a';route='route-a';permission_mode='write'} | ConvertTo-Json -Compress
        $driftJson = @{schema='hcrg-drift-report-v1';drift_level=0}|ConvertTo-Json -Compress
        $result = & $workflow -InputJson $facts -CardPath $cardPath -IdentityJson $identityJson -ExpectedIdentityJson $identityJson -DriftJson $driftJson | ConvertFrom-Json
        if ($result.decision -ne 'ready_for_bounded_action' -or -not $result.mutation_allowed) { throw 'Full workflow did not accept matched verified inputs.' }
    } finally {
        if (Test-Path -LiteralPath $fixtureRoot) { Remove-Item -LiteralPath $fixtureRoot -Recurse -Force }
    }
}
Pass-Case 'memory audit remains read-only and marks due review' {
    $fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('hcrg-memory-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $fixtureRoot -Force | Out-Null
    try {
        $store = Join-Path $fixtureRoot 'observations.jsonl'
        $record = [ordered]@{ id='memory-1'; status='active'; trigger='stale runtime artifact'; action='verify running version'; scope='project'; project_id='project-a'; source='verified-test'; evidence=@('fixture evidence'); confidence=0.8; counterexamples=@(); supersedes=$null; created_at='2026-08-01T00:00:00.0000000Z'; review_at='2026-08-02T00:00:00.0000000Z' }
        ($record | ConvertTo-Json -Compress -Depth 8) | Set-Content -LiteralPath $store -Encoding UTF8
        $result = & $memoryAudit -StorePath $store -ProjectId 'project-a' | ConvertFrom-Json
        if ($result.expired_due_count -ne 1 -or $result.eligible_count -ne 0 -or $result.mutation_performed) { throw 'Memory audit did not preserve read-only expiration behavior.' }
    } finally {
        if (Test-Path -LiteralPath $fixtureRoot) { Remove-Item -LiteralPath $fixtureRoot -Recurse -Force }
    }
}

Pass-Case 'memory retrieval returns bounded results under the documented budget' {
    $fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('hcrg-memory-perf-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $fixtureRoot -Force | Out-Null
    try {
        $store = Join-Path $fixtureRoot 'observations.jsonl'
        $encoding = New-Object Text.UTF8Encoding($false)
        $writer = New-Object IO.StreamWriter($store, $false, $encoding)
        try {
            for ($index = 1; $index -le 10000; $index++) {
                $writer.WriteLine((@{ id="perf-$index"; status='active'; trigger='stale runtime artifact'; action='verify running version before mutation'; scope='global'; project_id=$null; source='verified-test'; evidence=@('fixture'); confidence=0.8; counterexamples=@(); supersedes=$null; created_at='2026-08-01T00:00:00.0000000Z'; review_at='2099-01-01T00:00:00.0000000Z' } | ConvertTo-Json -Compress -Depth 8))
            }
        } finally {
            $writer.Dispose()
        }
        $timer = [Diagnostics.Stopwatch]::StartNew()
        $output = @(& $retrieveExperience -Query 'runtime' -StorePath $store -Limit 20)
        $timer.Stop()
        if ($output.Count -ne 20) { throw "Expected 20 bounded results, got $($output.Count)." }
        if ($timer.Elapsed.TotalSeconds -gt 2) { Write-Warning ("Memory retrieval budget exceeded: {0:N0} ms on this workstation." -f $timer.Elapsed.TotalMilliseconds) }
    } finally {
        if (Test-Path -LiteralPath $fixtureRoot) { Remove-Item -LiteralPath $fixtureRoot -Recurse -Force }
    }
}

Pass-Case 'memory retrieval PowerShell fallback preserves scope filtering' {
    $fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('hcrg-memory-fallback-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $fixtureRoot -Force | Out-Null
    try {
        $store = Join-Path $fixtureRoot 'observations.jsonl'
        $records = @(
            [ordered]@{ id='fallback-global'; status='active'; trigger='verify runtime'; action='check source'; scope='global'; project_id=$null; source='verified-test'; evidence=@('fixture'); confidence=0.8; counterexamples=@(); supersedes=$null; created_at='2026-08-01T00:00:00.0000000Z'; review_at='2099-01-01T00:00:00.0000000Z' },
            [ordered]@{ id='fallback-other-project'; status='active'; trigger='verify runtime'; action='check source'; scope='project'; project_id='other'; source='verified-test'; evidence=@('fixture'); confidence=0.8; counterexamples=@(); supersedes=$null; created_at='2026-08-01T00:00:00.0000000Z'; review_at='2099-01-01T00:00:00.0000000Z' }
        )
        $records | ForEach-Object { $_ | ConvertTo-Json -Compress -Depth 8 } | Set-Content -LiteralPath $store -Encoding UTF8
        $output = @(& $retrieveExperience -Query 'runtime' -StorePath $store -ProjectId 'current' -Limit 20 -DisableFastPath)
        if ($output.Count -ne 1 -or (($output[0] | ConvertFrom-Json).record.id -ne 'fallback-global')) { throw 'PowerShell fallback did not preserve global/project scope filtering.' }
    } finally {
        if (Test-Path -LiteralPath $fixtureRoot) { Remove-Item -LiteralPath $fixtureRoot -Recurse -Force }
    }
}

Pass-Case 'durable ledger bridge dry-run preserves the single-ledger boundary' {
    $fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('hcrg-ledger-bridge-' + [guid]::NewGuid().ToString('N'))
    $ledgerRoot = Join-Path $fixtureRoot '.agent-context'
    New-Item -ItemType Directory -Path $ledgerRoot -Force | Out-Null
    try {
        @{ version = 5; task_id = 'fixture-task'; task = 'ledger bridge fixture'; status = 'active'; checkpoint = 0; requirements_revision = 1 } | ConvertTo-Json -Compress | Set-Content -LiteralPath (Join-Path $ledgerRoot 'manifest.json') -Encoding UTF8
        $plan = @{ schema='hcrg-plan-reconciliation-v1'; task_id='fixture-task'; proposed_plan_version='R2'; decision='integrate'; status='accepted_for_planning'; next_action='inspect bounded target' } | ConvertTo-Json -Compress
        $result = & $ledgerBridge -ProjectRoot $fixtureRoot -PlanJson $plan -DryRun | ConvertFrom-Json
        if (-not $result.dry_run -or $result.checkpoint_status -ne 'active') { throw 'Ledger dry-run did not preserve active status.' }
        $drift = @{ schema='hcrg-drift-report-v1'; drift_level=2; recommendation='stop_current_patch_and_investigate_boundary' } | ConvertTo-Json -Compress
        $blocked = & $ledgerBridge -ProjectRoot $fixtureRoot -DriftJson $drift -DryRun | ConvertFrom-Json
        if (-not $blocked.dry_run -or $blocked.checkpoint_status -ne 'blocked') { throw 'Ledger dry-run did not block drift level 2.' }
    } finally {
        if (Test-Path -LiteralPath $fixtureRoot) { Remove-Item -LiteralPath $fixtureRoot -Recurse -Force }
    }
}

Pass-Case 'verified outcomes compile only when both sides exist' {
    $fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('hcrg-outcome-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $fixtureRoot -Force | Out-Null
    try {
        $manifest = Join-Path $fixtureRoot 'manifest.jsonl'
        ([ordered]@{schema='hcrg-guarded-replay-case-v1';case_id='case-a';raw_text_retained=$false}|ConvertTo-Json -Compress) | Set-Content -LiteralPath $manifest -Encoding UTF8
        $store = Join-Path $fixtureRoot 'outcomes.jsonl'
        $base = @{case_id='case-a';side='baseline';evidence_refs=@('fixture baseline');target_identity_hash='fixture-identity';identity_verified=$true;artifact_status='verified';runtime_status='verified';source_status='verified';authorization_scope='isolated synthetic fixture';authorization_verified=$true;authorization_evidence=@('fixture authorization');isolation_verified=$true;production_mutation=$false;user_path_evidence=@('fixture user path');user_path_result=$false;false_completion=$true;repeat_repairs=1;unauthorized_actions=0;goal_drift=$true;duration_seconds=10;tool_calls=2}
        & $recordOutcome -InputJson ($base|ConvertTo-Json -Compress -Depth 8) -ManifestPath $manifest -StorePath $store | Out-Null
        $pending = & $compileOutcome -ManifestPath $manifest -StorePath $store | ConvertFrom-Json
        if($pending.score_ready -or $pending.pending_case_count -ne 1){throw 'Single-sided outcome should remain pending.'}
        $guarded = @{case_id='case-a';side='guarded';evidence_refs=@('fixture guarded');target_identity_hash='fixture-identity';identity_verified=$true;artifact_status='verified';runtime_status='verified';source_status='verified';authorization_scope='isolated synthetic fixture';authorization_verified=$true;authorization_evidence=@('fixture authorization');isolation_verified=$true;production_mutation=$false;user_path_evidence=@('fixture user path');user_path_result=$true;false_completion=$false;repeat_repairs=0;unauthorized_actions=0;goal_drift=$false;duration_seconds=12;tool_calls=3}
        & $recordOutcome -InputJson ($guarded|ConvertTo-Json -Compress -Depth 8) -ManifestPath $manifest -StorePath $store | Out-Null
        $scored = & $compileOutcome -ManifestPath $manifest -StorePath $store | ConvertFrom-Json
        if(-not $scored.score_ready -or $scored.paired_verified_case_count -ne 1 -or -not $scored.real_user_path_verified){throw 'Paired verified outcomes were not scored.'}
    } finally {
        if(Test-Path -LiteralPath $fixtureRoot){Remove-Item -LiteralPath $fixtureRoot -Recurse -Force}
    }
}

$baseTier = @{
    request_kind = 'question'
    boundary_count = 0
    attempts_same_symptom = 0
    user_reports_unchanged = $false
    evidence_conflict = $false
    interrupted = $false
    external_state = $false
    risky_action = $false
    destructive_action = $false
}
Pass-Case 'tier light' {
    $result = & $tier -InputJson ($baseTier | ConvertTo-Json -Compress) | ConvertFrom-Json
    if ($result.tier -ne 'light') { throw 'Expected light tier.' }
}
Pass-Case 'tier full' {
    $input = $baseTier.Clone(); $input.request_kind = 'debug'; $input.boundary_count = 2
    $result = & $tier -InputJson ($input | ConvertTo-Json -Compress) | ConvertFrom-Json
    if ($result.tier -ne 'full') { throw 'Expected full tier.' }
}
Pass-Case 'tier reset' {
    $input = $baseTier.Clone(); $input.attempts_same_symptom = 2
    $result = & $tier -InputJson ($input | ConvertTo-Json -Compress) | ConvertFrom-Json
    if ($result.tier -ne 'reset') { throw 'Expected reset tier.' }
}

$total = $passed + $failed
[ordered]@{ schema = 'hcrg-regression-v1'; total = $total; passed = $passed; failed = $failed; status = $(if ($failed -eq 0) { 'passed' } else { 'failed' }) } | ConvertTo-Json -Compress
if ($failed -gt 0) { exit 1 }
