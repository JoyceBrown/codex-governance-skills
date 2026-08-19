param(
    [Parameter(Mandatory = $true)]
    [string]$InputJson,
    [string]$ManifestPath = (Join-Path $env:USERPROFILE '.codex\ai-experience\hcrg-evaluation\guarded-replay-manifest.jsonl'),
    [string]$StorePath = (Join-Path $env:USERPROFILE '.codex\ai-experience\hcrg-evaluation\verified-outcomes.jsonl')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$credentialPattern = '(?i)(Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})'
if ([Text.Encoding]::UTF8.GetByteCount($InputJson) -gt 16384 -or $InputJson -match $credentialPattern) { throw 'InputJson is oversized or credential-like.' }
if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { throw "ManifestPath does not exist: $ManifestPath" }
try { $input = $InputJson | ConvertFrom-Json } catch { throw 'InputJson must be valid JSON.' }
if ($null -eq $input -or $input -is [array]) { throw 'InputJson must contain one object.' }
$required = @('case_id','side','evidence_refs','target_identity_hash','identity_verified','artifact_status','runtime_status','source_status','authorization_scope','authorization_verified','authorization_evidence','isolation_verified','production_mutation','user_path_evidence','user_path_result','false_completion','repeat_repairs','unauthorized_actions','goal_drift','duration_seconds','tool_calls')
foreach ($field in $required) { if (-not ($input.PSObject.Properties.Name -contains $field)) { throw "Missing outcome field '$field'." } }
if ([string]$input.side -notin @('baseline','guarded')) { throw 'side must be baseline or guarded.' }
foreach ($field in @('identity_verified','authorization_verified','isolation_verified','production_mutation','false_completion','goal_drift','user_path_result')) { if ($input.$field -isnot [bool]) { throw "$field must be true or false." } }
foreach ($field in @('artifact_status','runtime_status','source_status')) { if ([string]$input.$field -ne 'verified') { throw "$field must be verified." } }
if (-not [bool]$input.identity_verified) { throw 'identity_verified must be true.' }
if ([string]::IsNullOrWhiteSpace([string]$input.authorization_scope)) { throw 'authorization_scope must be explicit.' }
if (-not [bool]$input.authorization_verified) { throw 'authorization_verified must be true.' }
if (-not [bool]$input.isolation_verified) { throw 'isolation_verified must be true.' }
if ([bool]$input.production_mutation) { throw 'production_mutation must be false.' }
foreach ($field in @('evidence_refs','authorization_evidence','user_path_evidence')) {
    $values = @($input.$field | ForEach-Object { [string]$_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($values.Count -eq 0) { throw "$field must contain at least one redacted reference." }
}
$repeat = 0; $unauthorized = 0; $duration = 0.0; $calls = 0
if (-not [int]::TryParse([string]$input.repeat_repairs,[ref]$repeat) -or $repeat -lt 0) { throw 'repeat_repairs must be a non-negative integer.' }
if (-not [int]::TryParse([string]$input.unauthorized_actions,[ref]$unauthorized) -or $unauthorized -lt 0) { throw 'unauthorized_actions must be a non-negative integer.' }
if (-not [double]::TryParse([string]$input.duration_seconds,[Globalization.NumberStyles]::Float,[Globalization.CultureInfo]::InvariantCulture,[ref]$duration) -or $duration -lt 0) { throw 'duration_seconds must be a non-negative number.' }
if (-not [int]::TryParse([string]$input.tool_calls,[ref]$calls) -or $calls -lt 0) { throw 'tool_calls must be a non-negative integer.' }
$caseIds = @{}
foreach ($line in Get-Content -LiteralPath $ManifestPath) { if ($line.Trim()) { $entry=$line|ConvertFrom-Json; $caseIds[[string]$entry.case_id]=$true } }
if (-not $caseIds.ContainsKey([string]$input.case_id)) { throw 'case_id is absent from the replay manifest.' }
if ([string]$input.target_identity_hash -notmatch '^[A-Za-z0-9._-]{8,128}$') { throw 'target_identity_hash must be a redacted stable identifier.' }
$output = [ordered]@{
    schema='hcrg-evaluation-outcome-v2'
    outcome_id=[guid]::NewGuid().ToString('N')
    case_id=[string]$input.case_id
    side=[string]$input.side
    verification_status='verified'
    target_identity_hash=[string]$input.target_identity_hash
    identity_verified=[bool]$input.identity_verified
    artifact_status='verified'
    runtime_status='verified'
    source_status='verified'
    authorization_scope=[string]$input.authorization_scope
    authorization_verified=[bool]$input.authorization_verified
    authorization_evidence=@($input.authorization_evidence)
    isolation_verified=[bool]$input.isolation_verified
    production_mutation=[bool]$input.production_mutation
    evidence_refs=@($input.evidence_refs)
    user_path_evidence=@($input.user_path_evidence)
    false_completion=[bool]$input.false_completion
    repeat_repairs=$repeat
    unauthorized_actions=$unauthorized
    goal_drift=[bool]$input.goal_drift
    user_path_passed=[bool]$input.user_path_result
    duration_seconds=$duration
    tool_calls=$calls
    verified_at=(Get-Date).ToUniversalTime().ToString('o')
    raw_text_retained=$false
}
$line = $output | ConvertTo-Json -Compress -Depth 8
if ($line -match $credentialPattern) { throw 'Refusing to write credential-like outcome.' }
$parent=Split-Path -Parent $StorePath
if($parent){New-Item -ItemType Directory -Path $parent -Force|Out-Null}
$stream=[IO.File]::Open($StorePath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
$writer=$null
try{$stream.Seek(0,[IO.SeekOrigin]::End)|Out-Null;$writer=New-Object IO.StreamWriter($stream,(New-Object Text.UTF8Encoding($false)));$writer.WriteLine($line);$writer.Flush()}finally{if($null -ne $writer){$writer.Dispose()}else{$stream.Dispose()}}
[ordered]@{schema='hcrg-evaluation-outcome-recorded-v2';case_id=$output.case_id;side=$output.side;verification_status='verified';raw_text_retained=$false}|ConvertTo-Json -Compress
