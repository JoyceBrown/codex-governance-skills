# Host adapter contract

This reference defines the minimum host surface needed to execute the orchestrator. It is a logical contract, not a request to create a second task database. An existing authoritative store may implement these records and operations.

The isolated reference implementation is [scripts/host_adapter.py](../scripts/host_adapter.py); its regression tests are [scripts/test_host_adapter.py](../scripts/test_host_adapter.py). They validate the state machine against a disposable SQLite store. The transport bridge in [scripts/app_server_bridge.py](../scripts/app_server_bridge.py) maps the host callbacks to Codex app-server `thread/*` and `turn/*` requests; unit tests use a fake JSON-RPC transport, while [scripts/live_app_server_smoke.py](../scripts/live_app_server_smoke.py) performs the separate live stdio contract check, including ephemeral notification-based result recovery and archive cleanup.

## Capability preflight

Before any dispatch, the commander asks the parent runtime or host for the current capabilities and target identity:

```text
resolve_project(project_id, plan_id, plan_revision, snapshot_id)
list_role_sessions(project_id, role_id, plan_id, snapshot_id)
resolve_role_session(project_id, role_id, parent_session_id, decision, candidate_session_id)
create_role_session(project_id, role_id, parent_session_id, plan_id, snapshot_id)
takeover_role_session(project_id, role_id, candidate_session_id, new_owner_session_id, expected_role_epoch, expected_lease_id)
prepare_session_handoff(project_id, role_id, old_session_id, new_session_id, host_identity_evidence)
commit_session_handoff(handoff_id, expected_epoch, expected_lease_id, checkpoint_ack)
recover_commander(project_id, old_session_id, new_session_id, host_identity_evidence)
create_local_child(parent_session_id, task_packet)
dispatch_task(task_packet)
dispatch_to_host(task_packet, send_task_callback)
record_local_child_result(parent_session_id, event_envelope)
record_event(event_envelope)
wake_session(session_id, receipt_id)
reconcile_attempt(project_id, task_id, attempt_id)
dependency_barrier_status(task_id)
recover_project(project_id, commander_epoch)
record_capability_check(capability_check)
archive_session(session_id)
retire_role_session(session_id, reason)
start_fresh_project(project_id, plan, snapshot, new_commander)
```

`resolve_project` binds the plan, plan revision and snapshot to one active commander lease and
rejects a second commander or a stale commander epoch. `recover_project` and
`reconcile_attempt` are read-side recovery operations; their absence is a
capability gap for durable roles. `record_capability_check` must persist the
preflight receipt rather than merely returning an in-memory result.

An explicit clean restart may use `start_fresh_project`. It retires the old
commander only after all project tasks are terminal and the host confirms the
old thread archive, then binds the new commander and plan in one update. It
does not run checkpoint/ACK handoff. If active tasks remain, it returns a
bounded `fresh_start_requires_reconciliation` receipt with those task IDs; it
does not wait indefinitely or silently discard them. Expired role sessions
have the analogous `retire_role_session` plus `create_role_session` path.

The three handoff operations above are **required host integration contracts**. The isolated SQLite reference adapter provides the durable `prepare_handoff()` / `commit_handoff()` state machine behind them, but it does not create a live successor, send a checkpoint, authenticate against Codex, or wake a real session. A host lacking those bindings must return `capability_gap` for `session_replace` or `commander_replace`; it must not treat successful ordinary dispatch as proof of replacement support.

`resolve_role_session` is mandatory before a durable role is created. It
returns `session_resolution_pending` and the compatible candidate IDs when a
candidate exists but `decision` is absent. `reuse` preserves the candidate's
owner and `role_epoch`; `new` creates a new role session; `takeover` changes the owner of the **same** role session and requires an
explicit authorization, validates the old lease/epoch, increments the epoch,
and returns a `handoff_receipt_id`. The host must never infer a user decision
from an idle session or create a duplicate while resolution is pending.

The logical session record therefore includes the project, role, plan and
snapshot boundary, lifecycle/health, permission boundary, owner, lease and
`role_epoch`. A resolution receipt records the candidate list, chosen action,
requesting owner, previous owner (for takeover), and timestamp. Callbacks from
an old takeover epoch are retained as `stale`.

The event source must be authenticated against the registered session and,
where the host supports it, an external host authenticator. Comparing an ID
string alone is insufficient. The task packet also binds a permission boundary
and an `acceptance_authority_session_id`; the worker may emit a completion claim,
while only the registered acceptance authority may emit `accepted` or
`rejected`. An independent validator uses `acceptance_mode=independent_validator`
and supplies a validation receipt for that acceptance scope. Event envelopes
carry `receipt_origin` (`worker_reported`, `parent_recorded`, `host_observed`, or
`adapter_generated`) and `observed_by`; `host_observed` requires an observer
identity. These fields describe provenance and do not replace host
authentication.

For `internal_child`, the parent runtime may satisfy `create_local_child` and `record_local_child_result` without a separate host session or wake call, but it must return a canonical child ID and a durable, replayable local receipt. For `main_session` and `commander`, the host must return a canonical session ID, role binding, project binding, permission boundary, leadership epoch and a durable receipt. A display name, cwd, title, UI icon, process ID or idle state is not a session identity.

If any required operation for the target kind is unavailable, the preflight result is a structured capability record:

```text
capability_check_id
project_id
plan_id
snapshot_id
target_kind
operation: dispatch | cleanup
transport: state_machine | host
required_capabilities
available_capabilities
missing_capabilities
canonical_target_id
checked_by
checked_at
result: ready | capability_gap | target_unresolved
```

The host or parent runtime may persist this check in its capability/audit stream, but must not create a task or attempt from it. The commander must not emit `task.dispatched` or claim that work was sent until the result is `ready`. The host may expose these operations through any approved transport; the Skill must not invent an API that the host has not provided.

`archive_session` is a separate cleanup capability. It must return `archived`/`closed` with a receipt that closes the parent-child edge, or `capability_gap` without mutating the target. `interrupt`/process exit alone is not deletion evidence.

For a one-shot worker, use `CodexAppServerBridge.start_task_session()` (which
forces `ephemeral=true`) and `LiveHostAdapter.create_task_session()`. Register
the returned canonical thread as `target_kind=internal_child`, execute the
bounded task, then call `close_task_session()` after the terminal callback.
`active_session_ids()` intentionally excludes these records; use the explicit
`active_task_session_ids()` diagnostic view when cleanup recovery needs them.

For a durable role rotation, use `LiveHostAdapter.replace_role_session()`.
It creates a new persistent thread and role instance, runs the state-machine
prepare/checkpoint/commit protocol, and only then archives the old host thread.
The result contains separate handoff and archive receipts, so a committed
handoff with failed cleanup is visible instead of being reported as complete.
The caller must confirm `safe_boundary=True` after reconciling external side
effects. `rotate_role_if_needed()` evaluates real host signals and only calls
replacement for `rotate_now` at that boundary. A prepared handoff with an
uncertain checkpoint keeps the successor for reconciliation; it must not be
silently deleted.

When the user intentionally discards an expired role's context, use
`LiveHostAdapter.replace_expired_role_session()`. It first verifies that the
old role has no non-terminal tasks, archives it, and creates a fresh role
session. No checkpoint or successor ACK is required because this is a new
baseline rather than a continuation.

The local Codex app-server currently acknowledges a successful `thread/archive`
request with an empty JSON object. The bridge maps that protocol response to an
explicit `result=archived` receipt; non-empty responses must carry `archived` or
`closed` status and are rejected otherwise.

For an ephemeral thread, the live server may remove the rollout before an
explicit archive call and answer `no rollout found`. The bridge maps that
response to `result=closed` only when the caller has already verified
`ephemeral=true`; durable sessions keep the fail-closed error. This makes
one-shot cleanup idempotent without turning a missing durable thread into a
false archive receipt.

The reference adapter also requires an authenticated actor for cleanup, refuses
to archive a session with open children, and clears its lifecycle and lease only
after the host archive callback succeeds.

The reference adapter's `dispatch()` is an isolated persistence primitive for
testing the state machine. It does not create a Codex thread or send a task to
another session. A real host must call `dispatch_to_host()` with a
`transport=host` preflight that includes `send_task` in the required capability
set and a callback that returns a durable host receipt:

```text
{"status":"delivered", "host_receipt_id":"...",
 "target_session_id":"...", "attempt_id":"..."}
```

Missing, malformed, mismatched, or uncertain send results are recorded in
`dispatch_deliveries` and seal the attempt as `unknown`; the adapter never
silently retries the send as a new attempt. A boolean `true` is accepted for a
minimal transport test, but production hosts should return the structured
receipt. This boundary makes the difference between a parent-recorded event
and a host-observed delivery explicit.

Capability checks are phase-specific. A dispatch preflight covers the
capabilities needed to resolve, send, persist, receive and recover the target;
cleanup runs a second preflight with `operation=cleanup`, whose required set
includes `archive_session`. A dispatch check must not be reused as evidence
that cleanup is available.

`wake_session(session_id, receipt_id)` is idempotent by `receipt_id`. A host
callback is required to mark delivery as `delivered`; an absent callback returns
`capability_gap`, and an uncertain callback is recorded as `unknown` for
reconciliation. An `unknown` delivery may be replayed with the same receipt ID;
once delivered, later calls are acknowledged as duplicates.

## Codex app-server bridge

For a local Codex installation, construct `CodexAppServerBridge.local()` with
the same `CODEX_HOME` used by the desktop runtime. It starts
`codex app-server --stdio`, performs the protocol handshake, and exposes
canonical thread resolution, start/resume/fork, task/checkpoint delivery and
archive operations. `start_session()` defaults to `ephemeral=false`, so the
returned thread is persisted in Codex's local thread store and can be listed
by the native client that uses the same state root.

`CodexAppServerBridge.local()` starts the managed stdio server during
construction and reports executable/startup failures as bounded
`app_server_unavailable` errors. `LiveHostAdapter.local()` is the convenience
entry point that creates this bridge on demand; it does not require the
desktop UI's private connection to be exposed.

The bridge is a transport binding, not a second orchestrator. It does not
claim that a separate stdio process is the desktop's live connection; a host
that needs one shared daemon must inject a JSON-RPC transport connected to the
managed app-server control socket. It also does not create a native handoff
button. PAO's SQLite lease and handoff state machine remains authoritative,
while app-server supplies the real thread/turn operations. Durable cloud
threads use the separate authenticated WebSocket host and are a capability
gap when that host is unavailable.

`probe_desktop_host(DesktopHostSnapshot(...))` is the fail-closed preflight for
that distinction. A private desktop `stdio` child, an unauthenticated durable
WebSocket, or an IPC endpoint that is not explicitly identified as the
app-server JSON-RPC transport returns `capability_gap` with evidence and does
not send a task. Pass `require_shared_host=True` and the snapshot to
`BridgeSupervisor` when the caller specifically requires the current desktop
connection; the default supervisor mode continues to support an explicitly
managed separate app-server process. On Windows, the current desktop runtime
exposes the local app-server as private stdio and `codex-ipc` as an IDE context
channel, so it must remain a capability gap until Codex exposes a verified
shared endpoint or an approved host adapter is injected.

`LiveHostAdapter` is the narrow composition point for the reference state
machine. It passes `CodexAppServerBridge.send_task()` to
`HostAdapter.dispatch_to_host()`, sends the durable handoff checkpoint through
`turn/start`, archives through `thread/archive`, and creates role sessions by
registering the canonical ID returned from `thread/start`. It does not make a
successful turn an acceptance decision; callbacks still have to be recorded
through the state adapter's event protocol.

`CodexAppServerBridge.read_task_turns()` reads durable turns through
`thread/read` with turns included, extracts only user messages carrying the
immutable PAO task packet, and returns bounded `TurnObservation` records. The
live app-server rejects that query for `ephemeral=true` threads, so the bridge
also consumes `item/*` and `turn/*` notifications into a bounded in-memory
ledger and uses that ledger for ephemeral results. A process restart cannot
replay an ephemeral result; it is reported as an explicit recovery gap and
must be reconciled as `unknown` by the PAO state machine. This prevents a
lost stdio connection from becoming a false completion. `LiveHostAdapter.ingest_thread_results()`
maps a terminal native turn to host-observed `task.started` and
`task.completed_claim`/`task.failed`/`task.unknown` events. The same turn ID is
used in the event ID and idempotency key, so replaying notifications is
idempotent. Acceptance remains a separate parent or validator event. When
the host supports it, the adapter sends the durable wake receipt back through
`turn/start`.

The local `turn/start` response only acknowledges that a turn was accepted and
started. It does not provide a structured acknowledgement that a successor
understood a handoff checkpoint. `send_checkpoint()` therefore returns
`delivered` until an injected host reports `acknowledged`; the handoff state
machine must keep the successor suspended and return `unknown` rather than
activating it on delivery alone.

The stdio bridge reconnects only after the child process has exited and
performs a fresh handshake. It does not infer success from a lost connection;
in-flight requests fail and must be reconciled by the PAO state machine. The
bridge also discards its in-memory ephemeral notification ledger on close or
reconnect, so partial results from the previous process cannot be reused as
completion evidence.

`BridgeSupervisor` is the bounded lifecycle runner for this facade. Its
`run_once()` reads a supplied finite session set and performs at most one
reconnect/replay after a transport failure. `run_bounded()` additionally
requires positive `max_cycles`, `max_seconds`, and `idle_cycles`; it stops on
the first idle threshold, time budget, terminal error, or cycle limit, and
closes the bridge by default. It is a pull operation with a receipt, not a
permanent polling thread. If no session set is supplied, it reads active
commander and role IDs from the authoritative PAO session table; it does not
guess from titles, sidebar entries, or conversation text.

## Atomic dispatch and event processing

`dispatch_task`/`dispatch_to_host` perform the following logical transaction:

1. Validate the active project, plan revision, snapshot, commander epoch, parent chain, dependency graph, lease and target session.
2. Reject `target_unresolved`, `multiple_parent`, `cycle_detected`, `commander_conflict`, `plan_drift`, expired lease or missing capability before creating a dispatch receipt.
3. Persist the immutable task package, ready capability-check reference, attempt, lease and `task.dispatched` receipt with a scoped idempotency key.
4. `dispatch_to_host` sends the package to the canonical target and records a host delivery receipt. An uncertain send outcome becomes `task.unknown`; it is never silently retried as a new attempt. A failed validation rolls back project/session/edge/task writes as one transaction. The isolated `dispatch()` primitive stops after step 3 and must not be presented as proof of host delivery.

`record_event` authenticates the emitter, validates the callback protocol, applies the per-attempt state machine, appends the event receipt, and updates the projection in one transaction or with an equivalent compare-and-swap. It returns `duplicate`, `accepted`, `stale`, `rejected`, `schema_unsupported` or `capability_gap`. Only after durable success may `wake_session` run.

Parent-only cancellation and unknown receipts are authenticated separately from
worker execution events. Event envelopes bind `cancel_epoch`; cancellation
increments the durable task epoch and a successful event can invoke the
idempotent parent wake callback immediately after commit.

## Minimum logical records

The authoritative store must be able to recover these records, even if their physical names differ:

- project and commander lease: project ID, commander session, epoch, expiry;
- capability checks: check ID, target kind, required/available/missing capabilities, canonical target, result and timestamp;
- session/role registry: canonical session ID, project, role, parent, permission boundary and lifecycle;
- task/attempt: immutable contract hash, plan revision, snapshot hash, attempt state, lease, cancel epoch and retry count;
- coordination profile: selected pattern, SOP step, fan-out group/limit, route key, handoff target and termination conditions;
- event receipts: event ID, scoped idempotency key, sequence, authenticated emitter, event/status pair, payload references and stale/rejection reason;
- acceptance receipts: acceptance scope, validation receipt, validator session, verdict and worker attempt;
- dependency/barrier state: parent task, dependency tasks, join policy, accepted receipts and matching project/plan-revision/snapshot/commander context;
- dispatch deliveries, wake deliveries and checkpoints: receipt ID, task/attempt or parent session, target, host receipt, delivery attempt, acknowledgement and recovery cursor.

Thread history, process state, UI projections and plain chat transcripts may be supporting evidence, but they cannot replace these logical records for callback acceptance or recovery.

## Recovery and cancellation

`reconcile_attempt` reads the latest receipt, session/process state and authorized artifact references before retry. A timeout does not prove failure or success. An attempt sealed as `unknown`, `cancelled` or `plan_drift` cannot be revived; late events are retained as `stale`. Plan drift seals the attempt, increments `cancel_epoch`, releases or expires its lease and records who caused the transition. Cancellation increments `cancel_epoch`, records the authorized actor and is delivered to the target when the transport permits. If cancellation delivery is uncertain and side effects are possible, the commander must wait for reconciliation or obtain an explicit decision before retrying.

Retries keep the logical `task_id` but create a new `attempt_id`, lease and
idempotency scope after the previous attempt is sealed. The previous attempt is
retained in the attempt history and late callbacks remain `stale`. A dependency
barrier is persisted for every task; `all`, `any` and explicit
`{"mode":"bounded_partial","min_accepted":N}` policies report `waiting`,
`ready` or `blocked` as dependency receipts change. A worker cannot enter
`task.started` while its barrier is not `ready`; the parent must wait for the
durable dependency receipt and then send or resume it. The adapter exposes this
projection but does not decide the project's next task.

The host adapter transports identity and evidence references. It does not decide whether a deliverable satisfies domain acceptance criteria or whether the next project task is correct; those decisions remain with the responsible parent and project authority.

## Coordination profile and idempotency boundaries

The immutable task packet may include `coordination_profile` with one of the
patterns `sequential`, `sop`, `fan_out`, `conditional` or `handoff`. Every
profile carries non-empty `termination_conditions`. `sop` binds `sop_id` and
an optional step; `fan_out` binds `fanout_group_id` and a positive
`max_fanout`; `conditional` binds a persisted `route_key`; and `handoff`
binds an authenticated `handoff_target_session_id`. These fields describe
coordination only. They do not grant a new permission boundary or bypass
the parent chain.

The adapter enforces `max_fanout` as the number of non-terminal tasks in the
same project and fan-out group. Accepted, rejected, blocked, failed, cancelled,
unknown, and stale tasks release an active slot, so later waves can reuse the
same group. A fan-out task still needs its own capability check, target session,
attempt, lease and receipt. If a project also needs a cumulative lifetime cap,
that must be a separate field; `max_fanout` is not that cap. `dependency_task_ids`
and `join_policy` provide the fan-in barrier; an impossible bounded-partial
threshold is rejected before the dispatch receipt is written.

`idempotency_key` is globally unique in the reference store. A replay with the
same task and attempt is acknowledged as `duplicate`; reuse by another task
or attempt returns `idempotency_key_conflict` and has no state side effect.
