Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

$testRoots = @(
    (Join-Path $root 'tests'),
    (Join-Path $root 'skills\bootstrap-codex-project\tests'),
    (Join-Path $root 'skills\deliberate-project\tests'),
    (Join-Path $root 'skills\durable-context\tests')
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

$guardRegression = Join-Path $root 'skills\human-centered-reasoning-guard\scripts\run-regression-tests.ps1'
& $guardRegression
if ($LASTEXITCODE -ne 0) { throw 'Human-centered guard regression tests failed.' }

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
Write-Output 'Integrated repository validation passed.'
