param(
    [Parameter(Mandatory = $true)]
    [string]$StorePath,
    [string]$ProjectId,
    [switch]$IncludeCandidates
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $StorePath -PathType Leaf)) { throw "Memory store does not exist: $StorePath" }
& (Join-Path $PSScriptRoot 'validate-memory.ps1') -StorePath $StorePath | Out-Null

$latest = @{}
foreach ($line in Get-Content -LiteralPath $StorePath) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $record = $line | ConvertFrom-Json
    $latest[[string]$record.id] = $record
}
$now = (Get-Date).ToUniversalTime()
$eligible = @()
$expired = @()
$conflicts = @()
$scopeCounts = @{}
foreach ($record in $latest.Values) {
    if ($record.status -eq 'expired' -or $record.status -eq 'superseded') { continue }
    if (-not $IncludeCandidates -and $record.status -ne 'active') { continue }
    if ($record.scope -eq 'project' -and -not [string]::IsNullOrWhiteSpace($ProjectId) -and [string]$record.project_id -ne $ProjectId) { continue }
    $reviewAt = [DateTime]::MinValue
    $isExpired = [DateTime]::TryParse([string]$record.review_at, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind, [ref]$reviewAt) -and $reviewAt.ToUniversalTime() -lt $now
    $scopeKey = "{0}:{1}" -f [string]$record.scope, [string]$record.project_id
    if (-not $scopeCounts.ContainsKey($scopeKey)) { $scopeCounts[$scopeKey] = 0 }
    $scopeCounts[$scopeKey] = [int]$scopeCounts[$scopeKey] + 1
    if ($isExpired) { $expired += [string]$record.id; continue }
    $eligible += [string]$record.id
}

$active = @($latest.Values | Where-Object { $_.status -eq 'active' -and ($_.scope -eq 'global' -or [string]::IsNullOrWhiteSpace($ProjectId) -or [string]$_.project_id -eq $ProjectId) })
for ($left = 0; $left -lt $active.Count; $left++) {
    for ($right = $left + 1; $right -lt $active.Count; $right++) {
        $a = $active[$left]; $b = $active[$right]
        if ([string]$a.scope -ne [string]$b.scope) { continue }
        if ([string]$a.scope -eq 'project' -and [string]$a.project_id -ne [string]$b.project_id) { continue }
        $aTerms = @(([string]$a.trigger + ' ' + [string]$a.action) -split '\s+' | Where-Object { $_.Length -ge 4 })
        $bText = ([string]$b.trigger + ' ' + [string]$b.action)
        $overlap = @($aTerms | Where-Object { $bText.Contains($_) }).Count
        if ($overlap -ge 2 -and [string]$a.action -ne [string]$b.action) {
            $conflicts += [ordered]@{ left_id=[string]$a.id; right_id=[string]$b.id; overlap_terms=$overlap; status='needs_review' }
        }
    }
}
[ordered]@{
    schema = 'hcrg-experience-audit-v1'
    audited_at = $now.ToString('o')
    record_count = $latest.Count
    eligible_count = $eligible.Count
    expired_due_count = $expired.Count
    conflict_count = $conflicts.Count
    eligible_ids = @($eligible)
    expired_due_ids = @($expired)
    conflicts = @($conflicts)
    scope_counts = @($scopeCounts.GetEnumerator() | ForEach-Object { [ordered]@{scope=$_.Key;count=$_.Value} })
    mutation_performed = $false
} | ConvertTo-Json -Depth 8
