Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
python -X utf8 -m unittest discover -s (Join-Path $root 'tests') -v
if ($LASTEXITCODE -ne 0) { throw 'Integrated repository contract tests failed.' }
$codexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$validator = Join-Path $codexRoot 'skills\.system\skill-creator\scripts\quick_validate.py'
foreach ($skill in Get-ChildItem -LiteralPath (Join-Path $root 'skills') -Directory) {
    python -X utf8 $validator $skill.FullName
    if ($LASTEXITCODE -ne 0) { throw "Skill validation failed: $($skill.Name)" }
}
Write-Output 'Integrated repository validation passed.'
