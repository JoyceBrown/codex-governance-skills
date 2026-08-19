param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('inspect', 'mutate', 'complete')]
    [string]$ActionType,
    [Parameter(Mandatory = $true)]
    [string]$GoalJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$MaxBytes = 12288
if ([Text.Encoding]::UTF8.GetByteCount($GoalJson) -gt $MaxBytes) { throw "GoalJson exceeds $MaxBytes bytes." }
if ($GoalJson -match '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})') { throw 'Credential-like value detected; redact goal facts before gating.' }
try { $goal = $GoalJson | ConvertFrom-Json } catch { throw 'GoalJson must be valid JSON.' }
if ($null -eq $goal -or $goal -is [array]) { throw 'GoalJson must contain one object.' }

$required = @{
    inspect = @('current_user_instruction', 'real_user_goal', 'visible_success', 'proposed_action', 'predicted_effect', 'discriminating_check', 'expected_observation', 'failure_signal', 'baseline', 'non_goals')
    mutate = @('current_user_instruction', 'real_user_goal', 'visible_success', 'proposed_action', 'predicted_effect', 'discriminating_check', 'expected_observation', 'failure_signal', 'target', 'source_of_truth', 'authorization', 'rollback', 'baseline', 'non_goals')
    complete = @('current_user_instruction', 'real_user_goal', 'visible_success', 'proposed_action', 'predicted_effect', 'evidence', 'user_path_result', 'source_of_truth', 'baseline', 'non_goals')
}

foreach ($field in $required[$ActionType]) {
    if (-not ($goal.PSObject.Properties.Name -contains $field)) { throw "Goal integrity blocked ${ActionType}: missing $field" }
    $values = @($goal.$field | ForEach-Object { [string]$_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($values.Count -eq 0) { throw "Goal integrity blocked ${ActionType}: empty $field" }
}

if ($ActionType -eq 'complete' -and ([string]$goal.user_path_result).ToLowerInvariant() -notin @('pass', 'passed', 'success', 'succeeded')) {
    throw 'Goal integrity blocked complete: user_path_result must be a verified pass.'
}
Write-Output "Goal integrity passed: $ActionType"
