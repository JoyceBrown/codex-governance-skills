Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

# Enforce the repository's release metadata rule for both committed and
# working-tree changes. CI supplies its base/head through the GitHub event;
# local runs also inspect staged and unstaged files.
$releaseMetadataValidator = Join-Path $root 'scripts\validate-release-metadata.py'
python -X utf8 $releaseMetadataValidator --include-worktree
if ($LASTEXITCODE -ne 0) { throw 'Release metadata validation failed.' }

# Validate published examples against the same contracts used by callers.
# Composition envelopes have a closed schema; other examples use the shared
# artifact-v1 envelope. This keeps examples useful without pretending that one
# schema owns every local Skill output.
$artifactValidator = Join-Path $root 'scripts\validate-artifacts.py'
$compositionValidator = Join-Path $root 'scripts\validate-composition.py'
foreach ($example in Get-ChildItem -LiteralPath (Join-Path $root 'examples') -Recurse -Filter '*.json' -File) {
    $document = Get-Content -LiteralPath $example.FullName -Raw | ConvertFrom-Json
    if ($document.PSObject.Properties.Name -contains 'schema_version' -and $document.schema_version -eq 'composition-v1') {
        python -X utf8 $compositionValidator $example.FullName
    } else {
        python -X utf8 $artifactValidator $example.FullName
    }
    if ($LASTEXITCODE -ne 0) { throw "Published example validation failed: $($example.FullName)" }
}

$testRoots = @(
    (Join-Path $root 'tests'),
    (Join-Path $root 'skills\bootstrap-codex-project\tests'),
    (Join-Path $root 'skills\deliberate-project\tests'),
    (Join-Path $root 'skills\durable-context\tests'),
    (Join-Path $root 'skills\human-centered-reasoning-guard\tests'),
    (Join-Path $root 'skills\execution-reliability\tests'),
    (Join-Path $root 'skills\intent-alignment\tests'),
    (Join-Path $root 'skills\diagnose\tests'),
    (Join-Path $root 'skills\tdd-loop\tests'),
    (Join-Path $root 'skills\architecture-health\tests'),
    (Join-Path $root 'skills\capability-director\tests')
)
foreach ($testRoot in $testRoots) {
    $testProject = Split-Path -Parent $testRoot
    Push-Location $testProject
    try {
        python -X utf8 -m unittest discover -s 'tests' -v
        if ($LASTEXITCODE -ne 0) { throw "Python tests failed: $testRoot" }
    } finally {
        Pop-Location
    }
}

$paoRoot = Join-Path $root 'skills\project-agent-orchestrator'
Push-Location $paoRoot
try {
    python -X utf8 -m unittest discover -s 'scripts' -p 'test_*.py' -v
    if ($LASTEXITCODE -ne 0) { throw 'Project Agent Orchestrator regression tests failed.' }
} finally {
    Pop-Location
}

$guardRegression = Join-Path $root 'skills\human-centered-reasoning-guard\scripts\run-regression-tests.ps1'
& $guardRegression
if ($LASTEXITCODE -ne 0) { throw 'Human-centered guard regression tests failed.' }

python -X utf8 (Join-Path $root 'skills\human-centered-reasoning-guard\validate_package.py')
if ($LASTEXITCODE -ne 0) { throw 'Human-centered guard package validation failed.' }

$codexRoot = if (-not [string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
    $env:CODEX_HOME
} else {
    $userHome = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
    if ([string]::IsNullOrWhiteSpace($userHome)) { $null } else { Join-Path $userHome '.codex' }
}
$validator = if ($codexRoot) { Join-Path $codexRoot 'skills\.system\skill-creator\scripts\quick_validate.py' } else { $null }
if ($validator -and (Test-Path -LiteralPath $validator)) {
    foreach ($skill in Get-ChildItem -LiteralPath (Join-Path $root 'skills') -Directory) {
        python -X utf8 $validator $skill.FullName
        if ($LASTEXITCODE -ne 0) { throw "Skill validation failed: $($skill.Name)" }
    }
} else {
    Write-Warning 'skill-creator quick_validate.py is unavailable; repository and embedded tests still ran.'
}

# Exercise the real installer against an isolated temporary destination. This
# catches packaging/path regressions without touching the user's Codex skills.
$smokeRoot = Join-Path ([IO.Path]::GetTempPath()) ('codex-governance-install-smoke-' + [guid]::NewGuid().ToString('N'))
$smokeTarget = Join-Path $smokeRoot 'skills'
try {
    New-Item -ItemType Directory -Force -Path $smokeRoot | Out-Null
    $installOutput = & (Join-Path $root 'scripts\install.ps1') -TargetSkillsRoot $smokeTarget -Names @('intent-alignment', 'durable-context')
    if ($LASTEXITCODE -ne 0) { throw 'Installer smoke test failed.' }
    foreach ($name in @('intent-alignment', 'durable-context')) {
        $installedSkill = Join-Path (Join-Path $smokeTarget $name) 'SKILL.md'
        if (-not (Test-Path -LiteralPath $installedSkill -PathType Leaf)) {
            throw "Installer smoke test did not install $name."
        }
    }
    if (@(Get-ChildItem -LiteralPath $smokeTarget -Directory).Count -ne 2) {
        throw 'Installer smoke test installed an unexpected Skill count.'
    }
} finally {
    if (Test-Path -LiteralPath $smokeRoot) {
        Remove-Item -LiteralPath $smokeRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
Write-Output 'Integrated repository validation passed.'
