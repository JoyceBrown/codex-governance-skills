param(
    [string]$EvaluationDirectory,
    [string]$ExperienceStore
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$codexHome = if (-not [string]::IsNullOrWhiteSpace($env:CODEX_HOME)) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
if ([string]::IsNullOrWhiteSpace($EvaluationDirectory)) { $EvaluationDirectory = Join-Path $codexHome 'ai-experience\hcrg-evaluation' }
if ([string]::IsNullOrWhiteSpace($ExperienceStore)) { $ExperienceStore = Join-Path $codexHome 'ai-experience\observations.jsonl' }
$skillRoot = Split-Path -Parent $PSScriptRoot
$checks = @()
function Run-Check([string]$Name, [scriptblock]$Operation) {
    try { & $Operation | Out-Null; $script:checks += [ordered]@{name=$Name;status='passed'} }
    catch { $script:checks += [ordered]@{name=$Name;status='failed';reason=$_.Exception.Message} }
}

Run-Check 'regression' { & (Join-Path $PSScriptRoot 'run-regression-tests.ps1') }
Run-Check 'adversarial' { & (Join-Path $PSScriptRoot 'run-adversarial-tests.ps1') -EvaluationDirectory $EvaluationDirectory }
Run-Check 'evaluation_artifacts' { & (Join-Path $PSScriptRoot 'validate-evaluation-artifacts.ps1') -EvaluationDirectory $EvaluationDirectory }
Run-Check 'powershell_parse' {
    $errors = @()
    Get-ChildItem $skillRoot -Recurse -Filter *.ps1 | ForEach-Object {
        $tokens = $null; $parseErrors = $null
        [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$parseErrors) | Out-Null
        if ($parseErrors.Count) { $errors += $_.FullName }
    }
    if ($errors.Count) { throw "Parse errors: $($errors -join ', ')" }
}
Run-Check 'python_parse' {
    $pythonScript = Join-Path $PSScriptRoot 'retrieve-experience-fast.py'
    $python = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($null -eq $python) { return }
    & $python.Source -3 -c "import ast, pathlib, sys; ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))" $pythonScript
    if ($LASTEXITCODE -ne 0) { throw "Python parse exited with $LASTEXITCODE" }
}
Run-Check 'skill_structure' {
    $validator = Join-Path $codexHome 'skills\.system\skill-creator\scripts\quick_validate.py'
    & py -3 $validator $skillRoot | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "quick_validate exited with $LASTEXITCODE" }
}
if (Test-Path -LiteralPath $ExperienceStore -PathType Leaf) {
    Run-Check 'experience_store' { & (Join-Path $PSScriptRoot 'audit-experience-store.ps1') -StorePath $ExperienceStore -IncludeCandidates }
} else {
    $checks += [ordered]@{name='experience_store';status='pending';reason='candidate experience store has not been initialized'}
}

$replayPending = $true
$coverage = $null
try {
    $replay = Get-Content (Join-Path $EvaluationDirectory 'replay-manifest-report.json') -Raw | ConvertFrom-Json
    $coverage = Get-Content (Join-Path $EvaluationDirectory 'guard-coverage-report.json') -Raw | ConvertFrom-Json
    $replayPending = [int]$replay.guarded_replay_pending -gt 0
} catch {
    $checks += [ordered]@{name='replay_status';status='failed';reason='missing replay or coverage report'}
}
$failed = @($checks | Where-Object { $_.status -eq 'failed' }).Count
[ordered]@{
    schema='hcrg-release-verification-v1'
    verified_at=(Get-Date).ToUniversalTime().ToString('o')
    checks=$checks
    failed_check_count=$failed
    simulated_coverage_rate=if($null -ne $coverage){[double]$coverage.coverage_rate}else{$null}
    real_guarded_replay_pending=$replayPending
    completion_claim_allowed=$false
    status=if($failed -gt 0){'verification_failed'}elseif($replayPending){'guard_ready_replay_pending'}else{'guard_ready_real_replay_verified'}
} | ConvertTo-Json -Depth 8
