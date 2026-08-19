param(
    [Parameter(Mandatory = $true)]
    [string]$InputJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$MaxBytes = 16384
if ([Text.Encoding]::UTF8.GetByteCount($InputJson) -gt $MaxBytes) { throw "InputJson exceeds $MaxBytes bytes." }
if ($InputJson -match '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})') { throw 'Credential-like value detected; redact reconciliation facts.' }
try { $record = $InputJson | ConvertFrom-Json } catch { throw 'InputJson must be valid JSON.' }
if ($null -eq $record -or $record -is [array]) { throw 'InputJson must contain one object.' }

$required = @('task_id', 'current_plan_version', 'current_goal', 'new_instruction', 'goal_relation', 'decision', 'rationale', 'evidence', 'source_of_truth', 'impact', 'acceptance_delta', 'authorization', 'next_action')
foreach ($field in $required) {
    if (-not ($record.PSObject.Properties.Name -contains $field)) { throw "Missing reconciliation field '$field'." }
    $values = @($record.$field | ForEach-Object { [string]$_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($values.Count -eq 0 -and $field -notin @('authorization')) { throw "Reconciliation field '$field' must not be empty." }
}

$relations = @('same', 'refined', 'changed', 'conflict', 'unknown')
$decisions = @('integrate', 'defer', 'supersede', 'clarify')
$relation = [string]$record.goal_relation
$decision = [string]$record.decision
if ($relation -notin $relations) { throw "Invalid goal_relation: $relation" }
if ($decision -notin $decisions) { throw "Invalid decision: $decision" }

if ($relation -in @('conflict', 'unknown') -and $decision -ne 'clarify') { throw 'Conflicting or unknown goals require clarify.' }
if ($decision -eq 'integrate' -and $relation -notin @('same', 'refined')) { throw 'integrate requires a same or refined goal.' }
if ($decision -eq 'supersede' -and $relation -ne 'changed') { throw 'supersede requires a changed goal.' }
if ($decision -eq 'clarify' -and (-not ($record.PSObject.Properties.Name -contains 'open_question') -or [string]::IsNullOrWhiteSpace([string]$record.open_question))) { throw 'clarify requires open_question.' }
if ($decision -eq 'supersede' -and (-not ($record.PSObject.Properties.Name -contains 'supersedes_plan_version') -or [string]::IsNullOrWhiteSpace([string]$record.supersedes_plan_version))) { throw 'supersede requires supersedes_plan_version.' }
if ($decision -ne 'clarify' -and @($record.authorization).Count -eq 0) { throw "$decision requires explicit authorization." }

$nextVersion = if ($record.PSObject.Properties.Name -contains 'proposed_plan_version' -and -not [string]::IsNullOrWhiteSpace([string]$record.proposed_plan_version)) { [string]$record.proposed_plan_version } else { [string]$record.current_plan_version }
$status = if ($decision -eq 'clarify') { 'blocked_for_clarification' } else { 'accepted_for_planning' }
$output = [ordered]@{
    schema = 'hcrg-plan-reconciliation-v1'
    task_id = [string]$record.task_id
    current_plan_version = [string]$record.current_plan_version
    proposed_plan_version = $nextVersion
    goal_relation = $relation
    decision = $decision
    status = $status
    rationale = [string]$record.rationale
    impact = [string]$record.impact
    acceptance_delta = [string]$record.acceptance_delta
    evidence = @($record.evidence)
    source_of_truth = @($record.source_of_truth)
    next_action = [string]$record.next_action
}
if ($record.PSObject.Properties.Name -contains 'open_question') { $output['open_question'] = [string]$record.open_question }
if ($record.PSObject.Properties.Name -contains 'supersedes_plan_version') { $output['supersedes_plan_version'] = [string]$record.supersedes_plan_version }
$output | ConvertTo-Json -Depth 8
