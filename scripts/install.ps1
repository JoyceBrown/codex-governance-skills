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

$uniqueNames = @($Names | Select-Object -Unique)
if ($uniqueNames.Count -ne $Names.Count) { throw 'Names must not contain duplicates.' }

function Remove-InstallPath([string]$Path) {
    if (Test-Path -LiteralPath $Path -PathType Container) {
        [IO.Directory]::Delete($Path, $true)
    } elseif (Test-Path -LiteralPath $Path) {
        [IO.File]::Delete($Path)
    }
}

$transactionId = [guid]::NewGuid().ToString('N')
$backupStamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-' + $transactionId.Substring(0, 8)
$plans = @()

# Preflight every destination before touching any installed Skill.
foreach ($name in $Names) {
    $source = Join-Path $sourceRoot $name
    $destination = Join-Path $targetRoot $name
    if (-not (Test-Path -LiteralPath (Join-Path $source 'SKILL.md'))) { throw "Invalid Skill source: $source" }

    $destinationExists = Test-Path -LiteralPath $destination
    if ($destinationExists -and -not $Force) {
        throw "Destination exists: $destination. Re-run with -Force to create a backup first."
    }

    $staging = Join-Path $targetRoot ('.install-' + $name + '-' + $transactionId)
    if (Test-Path -LiteralPath $staging) { throw "Staging path already exists: $staging" }
    $backup = if ($destinationExists) { "$destination.backup-$backupStamp" } else { $null }
    if ($backup -and (Test-Path -LiteralPath $backup)) { throw "Backup path already exists: $backup" }

    $plans += [pscustomobject]@{
        Name = $name
        Source = $source
        Destination = $destination
        DestinationExists = $destinationExists
        Staging = $staging
        Backup = $backup
        BackupMoved = $false
        Installed = $false
    }
}

$receipt = @()
try {
    # Stage the complete bundle before changing any destination.
    foreach ($plan in $plans) {
        Copy-Item -LiteralPath $plan.Source -Destination $plan.Staging -Recurse
    }

    # Commit each staged directory; the catch block rolls back the whole bundle.
    foreach ($plan in $plans) {
        if ($plan.DestinationExists) {
            Move-Item -LiteralPath $plan.Destination -Destination $plan.Backup
            $plan.BackupMoved = $true
        }
        Move-Item -LiteralPath $plan.Staging -Destination $plan.Destination
        $plan.Installed = $true
        $receipt += [ordered]@{name=$plan.Name;destination=$plan.Destination;backup=$plan.Backup;status='installed'}
    }
} catch {
    $failure = $_
    $rollbackErrors = @()
    for ($index = $plans.Count - 1; $index -ge 0; $index--) {
        $plan = $plans[$index]
        try {
            if ($plan.Installed) { Remove-InstallPath $plan.Destination }
            if ($plan.BackupMoved -and (Test-Path -LiteralPath $plan.Backup) -and -not (Test-Path -LiteralPath $plan.Destination)) {
                Move-Item -LiteralPath $plan.Backup -Destination $plan.Destination
            }
            if (Test-Path -LiteralPath $plan.Staging) { Remove-InstallPath $plan.Staging }
        } catch {
            $rollbackErrors += "$($plan.Name): $($_.Exception.Message)"
        }
    }
    if ($rollbackErrors.Count -gt 0) {
        throw "Bundle install failed and rollback was incomplete: $($rollbackErrors -join '; '). Original: $($failure.Exception.Message)"
    }
    throw $failure
}

[ordered]@{
    schema = 'codex-governance-skills-install-v1'
    target_skills_root = $targetRoot
    transaction_id = $transactionId
    atomic = $true
    installed = $receipt
} | ConvertTo-Json -Depth 6
