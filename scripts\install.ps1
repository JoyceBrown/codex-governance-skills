param(
    [string]$TargetSkillsRoot,
    [string[]]$Names,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $repoRoot 'skills'
$known = @(
    'bootstrap-codex-project',
    'durable-context',
    'human-centered-reasoning-guard',
    'deliberate-project',
    'intent-alignment',
    'diagnose',
    'tdd-loop',
    'architecture-health',
    'capability-director'
)

if ([string]::IsNullOrWhiteSpace($TargetSkillsRoot)) {
    $codexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
    $TargetSkillsRoot = Join-Path $codexRoot 'skills'
}
if ($null -eq $Names -or $Names.Count -eq 0) { $Names = $known }

$unknown = @($Names | Where-Object { $_ -notin $known })
if ($unknown.Count -gt 0) { throw "Unknown Skill name(s): $($unknown -join ', ')" }

$targetRoot = [IO.Path]::GetFullPath($TargetSkillsRoot)
New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null
$receipt = @()

foreach ($name in $Names) {
    $source = Join-Path $sourceRoot $name
    $destination = Join-Path $targetRoot $name
    if (-not (Test-Path -LiteralPath (Join-Path $source 'SKILL.md'))) { throw "Invalid Skill source: $source" }
    if (Test-Path -LiteralPath $destination) {
        if (-not $Force) { throw "Destination exists: $destination. Re-run with -Force to create a backup first." }
    }

    $staging = Join-Path $targetRoot ('.install-' + $name + '-' + [guid]::NewGuid().ToString('N'))
    $backup = $null
    try {
        Copy-Item -LiteralPath $source -Destination $staging -Recurse
        if (Test-Path -LiteralPath $destination) {
            $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
            $backup = "$destination.backup-$stamp"
            if (Test-Path -LiteralPath $backup) { throw "Backup path already exists: $backup" }
            Move-Item -LiteralPath $destination -Destination $backup
        }
        Move-Item -LiteralPath $staging -Destination $destination
        $receipt += [ordered]@{name=$name;destination=$destination;backup=$backup;status='installed'}
    } catch {
        if (Test-Path -LiteralPath $staging) { [IO.Directory]::Delete($staging, $true) }
        if ($backup -and (Test-Path -LiteralPath $backup) -and -not (Test-Path -LiteralPath $destination)) {
            Move-Item -LiteralPath $backup -Destination $destination
        }
        throw
    }
}

[ordered]@{
    schema = 'codex-governance-skills-install-v1'
    target_skills_root = $targetRoot
    installed = $receipt
} | ConvertTo-Json -Depth 6

