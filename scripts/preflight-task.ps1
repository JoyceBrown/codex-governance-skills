param(
    [Parameter(Mandatory = $true)]
    [string]$CardPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'validate-task-card.ps1') -CardPath $CardPath | Out-Null
$card = Get-Content -Raw -LiteralPath $CardPath | ConvertFrom-Json
if ([string]$card.next_action -match '(?i)(delete|remove|migrate|restart|publish|deploy|replace|provider|account|network|production)') {
    if (@($card.authorization).Count -eq 0 -or @($card.baseline).Count -eq 0) {
        throw 'High-risk task requires explicit authorization and a baseline before tool execution.'
    }
}
Write-Output "Preflight passed: $($card.task_id) / plan $($card.plan_version)"
