# Optional HCR Host Contract

Contract: hcr-host-v1. This is an input/output adapter specification, not a new
Runtime, Hook, permission authority, plan, or persistence service. The only
discoverable skill remains `human-centered-reasoning-guard`.

## Authority and composition

The current user instruction and applicable host permissions constrain every
action. Bootstrap identifies project-file and plan ownership; Durable owns its
continuity lifecycle; Guard owns its existing action and completion checks.
The native host executes tools and reports observed results; runtime success
does not prove user acceptance.

HCR consumes bounded authorized projections and proposes candidates, anomalies,
or verification requests. It cannot lift a Guard block, change an approved
WHY/WHAT/route, publish, alter permissions, or mark the host task complete.
High-impact actions need the authorization required for that action; reuse
existing valid authorization rather than asking repeatedly. A low risk label
inside a node or model response cannot grant permission.

Use the collection envelope for cross-skill summaries: request_id, status,
scope, intent_status, evidence_refs, next_action, budget. Guard action fields
such as authorization, target and rollback remain available. Full experience
nodes belong only in a bounded local Replay request, not the shared prompt.

## Host context and telemetry

The host context schema is [hcr-host-context.schema.json](../schemas/hcr-host-context.schema.json).
It carries the current task/WHY/WHAT/constraints, runtime identity, epistemic and
requirement projections, and bounded experience references. Only supply fields
whose provenance and scope are known. It does not initiate a hook or background
poller.

Telemetry fields describe observed failure counts, same-region changes,
acceptance stagnation, goal progress, model/tool/time cost, repeated actions,
user signals, proxy completion, and pending high-impact actions. Count only the
same relevant target/hypothesis/version and event window; reset or mark unknown
when those change. Missing, stale, contradictory, or manually estimated counters
are not measured facts. Multiple correlated counters are not independent signals.

For manual fallback, use the label HCR_MANUAL_CONTEXT and this telemetry payload:

```json
{"telemetry_source": "manual", "telemetry_confidence": "unknown"}
```

Omit unavailable counters or use null where the schema permits it. Never invent
project/runtime IDs to pass validation. Without a structured host, the ordinary
Guard uses current authorized evidence and simply skips Replay.

The native host may signal a check, user-requested reasoning, repeated failure,
progress stall, contradiction, proxy completion or high-impact action. These
events are optional routing hints. No host implementation is included here.

## Knowledge and requirements

Epistemic records use `epistemic_status` for OBSERVATION, FACT, INFERENCE,
HYPOTHESIS, PREDICTION or UNKNOWN. A FACT needs evidence, source, scope and a
verification timestamp. Their presence is a structural check, not proof that
the evidence is true.

Optional `governance_status` and `governance_reference` reflect existing owner
decisions. HCR cannot create an ACCEPTED_DECISION or promote a hypothesis by
assigning a status. A promotion proposal goes back to the applicable owner.
A current requirement projection preserves ACTIVE, COMPLETED, SUPERSEDED and
REJECTED with source references. It never replaces current requirements or
creates another Requirement Ledger.

## Experience input and ownership

ExperienceNode is a read-only view of existing, authorized, reviewed records.
It contains node_id, goal, action, observed result/progress, scoped evidence,
applicability, costs and optional parent history. `active` here means eligible
for historical search, not approved for current execution or a globally active
principle. Superseded/retired history can explain provenance but is not recommended.

The original Guard `observations.jsonl` is a different format:
id/trigger/action/evidence/confidence/review_at do not establish
WHY/WHAT/result/goal_progress. Do not feed it directly into this evaluator or
guess missing values. A host adapter can map an ID and evidence references,
but must obtain the goal and actual outcome from their source records. Without
that evidence, omit the node; no eligible history is an ordinary fallback.

Keep the existing store and lifecycle. Apply its scope, privacy, review expiry
and conflict rules before exporting. Carry record IDs and evidence references
back to their authoritative source; a projection must be discardable and
reconstructable. Do not duplicate a store, scan a full chat archive, or write a
new event database as a prerequisite for using the skill.

## Replay request and result

From the installed Guard folder:

```powershell
python -X utf8 replay/evaluator.py examples/replay_request.json
```

The CLI and Python `evaluate` entrypoint validate input. Requests include:

- Nonempty why, what, project_id and environment_scope; `experience_nodes` is a
  required array and may be empty to represent a normal no-history fallback.
- Current constraints as an explicit string array; empty means none supplied.
  The evaluator requires the recorded applicability set to match this current
  set exactly. This is metadata matching, not semantic proof of constraint
  compliance.
- Optional runtime_id/dependencies and validity boundaries. A scoped historical
  prerequisite cannot be assumed valid when current context is missing.
- Strategy: goal_progress, low_cost, evidence_first or balanced priority;
  avoid_failure_classes, max_depth, early_stop_goal_progress, cost_weight and
  risk_weight. Legacy require_same_scope cannot disable project/environment
  isolation.

Only same-project/environment, active, evidenced and applicable nodes survive.
No cross-project global replay is inferred. An owner may separately propose
reusing an abstract global lesson through the existing memory rules and a current
verification check; that is outside this adapter's exact-scope contract.

The evaluator validates graph IDs/ancestry, finite and bounded numeric inputs,
request size, node count and depth. Limits are 2 MiB per CLI input, 1000 nodes,
32 depth, and 1000 paths. Depth-limited paths report truncation. Ranking respects
the selected strategy; path output includes historical node sequence, terminal
progress, accumulated cost and early-stop/truncation state. A failed ancestor
may be part of historical context; it is never a command to repeat that action.

The result is a candidate set, historical paths and an optional recommendation,
with llm_calls=0 and an explicit historical boundary. An empty recommendation
means history does not provide an eligible HOW. It does not block ordinary
read-only investigation or prove that a new architecture is required.

Scores are search utilities, not truth probabilities or authorization. Inspect
the record/path prerequisites and perform current verification before acting.
Do not evaluate node action strings as code. No model calls, project writes,
memory writes, networking, package installation or runtime actions occur in
the evaluator.

Schemas resolve from the bundled directory only through
[replay/schema_validation.py](../replay/schema_validation.py).
The validator deliberately supports only the bundled schema vocabulary and
rejects unsupported constructs and nonlocal references. It is not a general
JSON Schema engine. Package verification runs schema conformance and examples
offline using [validate_package.py](../validate_package.py).

## Return to reality and optional writeback

Only the native host performs the actual authorized verification. Distinguish
implementation tests, explicit requirement acceptance and the user outcome.
Replay cannot mark any of those complete.

After fresh execution, return bounded observation, test and candidate references
to the existing owner. If persistence is authorized, use that owner's normal
append/review/supersede workflow; if policy requires explicit memory permission,
leave a proposal until it is provided. HCR never writes through its own parallel
ledger or promotes a candidate automatically. A writeback object describes
proposed data; its existence is not a completed transaction.
