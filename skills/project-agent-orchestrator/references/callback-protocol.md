# Callback protocol

## Event model

`event_type` records what happened. `status` records the resulting state. They are two fields with an explicit one-to-one mapping; implementations must reject any other pair.

| event_type | status | emitter | meaning |
|---|---|---|---|
| `task.dispatched` | `dispatched` | adapter/commander | durable dispatch receipt exists |
| `task.started` | `running` | worker | worker accepted the attempt |
| `task.progress` | `running` | worker | non-terminal progress |
| `task.waiting` | `waiting` | worker/parent | dependency or human input is pending |
| `task.completed_claim` | `completed_claim` | worker | worker claims its assigned scope is finished |
| `task.partial` | `partial` | worker | only part of the authorized scope is finished |
| `task.blocked` | `blocked` | worker | worker cannot proceed within scope |
| `task.failed` | `failed` | worker/adapter | execution ended with a known failure |
| `task.cancelled` | `cancelled` | parent/adapter | cancellation was authorized and recorded |
| `task.unknown` | `unknown` | adapter/parent | outcome could not be established; the attempt is sealed |
| `task.accepted` | `accepted` | registered acceptance authority | claim validated or a partial result explicitly allowed |
| `task.rejected` | `rejected` | registered acceptance authority | claim rejected with the required correction |
| `task.stale` | `stale` | adapter | late, superseded or plan-drifted event; it cannot advance work |

`task.completed_claim` is never acceptance. An unaccepted completion claim may receive one parent verdict (`accepted` or `rejected`), or be sealed as `unknown` when a handoff or recovery leaves the outcome unverified. `task.unknown` and `task.cancelled` seal the attempt; a late event from either attempt is `stale`. A new execution always receives a new `attempt_id`.

Every event also carries `receipt_origin` and `observed_by`. `worker_reported`
means the worker supplied the event, `parent_recorded` means the immediate
parent recorded a result, `host_observed` means a host integration supplied an
observer identity, and `adapter_generated` is reserved for adapter receipts.
`host_observed` without `observed_by` is rejected. Provenance labels make the
trust level visible; they do not turn a parent transcription into independent
host evidence.

Allowed transitions are bounded: `dispatched -> running|waiting|cancelled|unknown`; `running -> running|waiting|completed_claim|partial|blocked|failed|cancelled|unknown`; `waiting -> running|cancelled|unknown`; `completed_claim|partial -> accepted|rejected|unknown`; and `blocked|failed|cancelled|unknown|accepted|rejected|stale` have no forward transition within the attempt. An adapter rejects any other transition before waking the parent.

## Event envelope

```json
{
  "schema_version": 2,
  "event_id": "evt-...",
  "event_type": "task.completed_claim",
  "status": "completed_claim",
  "project_id": "project-...",
  "plan_id": "plan-...",
  "plan_revision": "rev-...",
  "snapshot_id": "snapshot-...",
  "snapshot_hash": "sha256:...",
  "capability_check_id": "cap-...",
  "permission_boundary": "boundary-...",
  "acceptance_mode": "commander_gate|independent_validator",
  "acceptance_authority_session_id": "session-...",
  "acceptance_authority_permission_boundary": "boundary-...",
  "acceptance_scope_id": "acceptance-...",
  "validation_receipt_id": "validation-...",
  "session_resolution": "reuse|takeover|new",
  "candidate_session_ids": ["session-..."],
  "role_epoch": 2,
  "previous_owner_session_id": "session-...",
  "handoff_receipt_id": "handoff-...",
  "coordination_profile": {
    "pattern": "sequential|sop|fan_out|conditional|handoff",
    "sop_id": "...",
    "sop_step": "...",
    "fanout_group_id": "...",
    "max_fanout": 10,
    "route_key": "...",
    "handoff_target_session_id": "...",
    "termination_conditions": ["accepted", "rejected", "blocked", "failed", "cancelled", "unknown"]
  },
  "task_id": "task-...",
  "attempt_id": "attempt-...",
  "task_contract_hash": "sha256:...",
  "root_session_id": "session-...",
  "session_id": "session-...",
  "target_session_id": "session-...",
  "role_id": "role-...",
  "parent_session_id": "session-...",
  "callback_to": "session-...",
  "commander_epoch": "epoch-...",
  "emitted_by_session_id": "session-...",
  "receipt_origin": "worker_reported|parent_recorded|host_observed|adapter_generated",
  "observed_by": "host-or-parent-principal",
  "sequence": 12,
  "receipt_sequence": 1042,
  "completed_scope": ["..."],
  "deliverables": ["..."],
  "evidence_refs": ["..."],
  "open_items": ["..."],
  "blockers": ["..."],
  "wake_condition": "...",
  "rejection_reasons": ["..."],
  "cancelled_by_session_id": "session-...",
  "cancel_epoch": "epoch-...",
  "stale_reason": "plan_drift|late_attempt|sealed_attempt|schema_unsupported",
  "stale_by_session_id": "session-...",
  "supersedes_event_id": "evt-...",
  "accepted_for_event_id": "evt-...",
  "validated_by_session_id": "session-...",
  "validation_evidence_refs": ["..."],
  "emitted_at": "2026-01-01T00:00:00Z",
  "idempotency_key": "project-.../task-.../attempt-.../event-..."
}
```

Fields that do not apply may be empty, but identity, plan/snapshot, target and callback fields must match the immutable task package. `accepted_for_event_id`, `validated_by_session_id` and `validation_evidence_refs` are required for `task.accepted`; a rejected claim requires `rejection_reasons`. Do not put raw transcripts, secrets or full tool logs in the envelope.

`schema_version: 2` is the canonical form. An adapter must publish the versions it can validate and the corresponding upcaster. An unsupported version returns `schema_unsupported` without storing or waking; an upcast event retains the original version and transformation receipt for replay. Schema migration never changes project, task, attempt, plan or evidence identity.

## Validation, ordering and replay

The adapter authenticates `emitted_by_session_id` and binds it to the registered session, role, project and permission boundary. For adapter-generated events, it authenticates the registered adapter principal instead of inventing a worker session. String equality of IDs is not source authentication. It validates project, plan revision, snapshot hash, task, attempt, parent, target, commander epoch, callback target, acceptance authority, schema version and the event/status pair before storing an event.

`sequence` is the source sequence, contiguous and starting at 1 within one `(task_id, attempt_id)` stream. `receipt_sequence` is assigned by the adapter in the append-only receipt stream and is the only ordering field for adapter-generated `task.stale` or capability records. Optional progress may be omitted; a terminal event cannot skip a required predecessor. A duplicate `event_id` or scoped `idempotency_key` is acknowledged without redispatch. A second terminal event for the same attempt is rejected or marked `stale`; it never rewrites the first terminal event. A late event from an older attempt, sealed `unknown`/`cancelled` attempt, or older plan revision is stored as `stale` with its original source sequence and `supersedes_event_id`; it does not advance the active attempt or wake the parent.

The reference store treats `idempotency_key` as globally unique. Reusing a key
for another task or attempt is an `idempotency_key_conflict`, not a duplicate;
the adapter must leave both task projections unchanged.

The adapter must atomically commit the receipt and the task state transition before waking the immediate parent. Wake delivery is at-least-once and separately deduplicated by receipt ID; a lost wake is recoverable from the durable receipt stream.

## Waiting, failure, cancellation and retry

- `task.waiting` includes a concrete `wake_condition` and a dependency or input reference. It is not a terminal event.
- A task with dependencies cannot emit `task.started` until its persisted barrier is `ready`; it must remain `waiting` while required receipts are unresolved.
- `task.blocked` names the smallest escalation or evidence needed; it may be retried only after the parent authorizes a new attempt.
- A terminal source event whose status is absent from the packet's `termination_conditions` is rejected as `termination_condition_violation`; the profile cannot silently claim a different stopping rule.
- `task.failed` includes bounded diagnostic references and the failed attempt.
- `task.cancelled` includes `cancelled_by_session_id` and the current `cancel_epoch`.
- `task.unknown` means timeout, interruption, lost session or missing callback prevented outcome determination. It seals the attempt. Reconcile process, session, task and artifact state before creating a new attempt; unknown external side effects require an explicit parent decision before retry.
- Retry keeps the logical `task_id` but creates a new `attempt_id`, lease and idempotency scope, subject to `max_attempts`. The previous attempt is retained in attempt history; it never overwrites the previous terminal event and never assumes the old worker stopped. Late callbacks from that history are stored as `stale`.
- A handoff is a waiting/dispatch decision with an authenticated target and a durable wake receipt. It is not an acceptance decision and cannot bypass the immediate parent.
- Termination conditions are explicit in the task contract. A loop without an accepted/rejected/blocked/failed/cancelled/unknown path, deadline, cancellation path or bounded attempt count is not dispatchable.
- When the active plan or snapshot revision changes, the adapter seals affected attempts, increments `cancel_epoch`, releases or expires their lease, records `task.stale` with `stale_reason=plan_drift`, and makes a best-effort cancellation notification. Continued work requires a new contract and `attempt_id`; no revision change is silently accepted.

## Parent and acceptance responsibility

For an internal child, the parent runtime normally receives the result directly, then emits any formal parent summary. For a durable role main session, the host receives the role's formal terminal callback and makes it available to the project commander. The parent chain is therefore:

```text
internal child -> immediate parent main session -> project commander
durable main session -> project commander
```

Only the registered `acceptance_authority_session_id` may emit `task.accepted` or `task.rejected`. By default this is the responsible parent; `acceptance_mode=independent_validator` may bind it to a registered acceptance session with a distinct `acceptance_authority_permission_boundary`. The project plan advances only after the plan-owning authority accepts the result and all required dependency barriers are satisfied. Barriers use `all`, `any`, or an explicit `{"mode":"bounded_partial","min_accepted":N}` policy and expose `waiting`, `ready`, or `blocked` state. UI spinners, process exit, an idle conversation or a plain-text `done` message are observations only; they are not terminal receipts.
