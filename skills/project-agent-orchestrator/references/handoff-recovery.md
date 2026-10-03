# Session handoff and recovery

This protocol transfers a project responsibility between canonical sessions. The project, plan, role, evidence and acceptance policy survive a session change; a session ID does not. Use it for an ordinary planned replacement as well as a lost, archived, inaccessible or reinstalled session. A different process, model or chat title does not by itself prove that an old session is gone.

## Decision and evidence

First query the host by canonical ID and project binding, including active and archived records. Distinguish `available`, `archived_but_recoverable`, `verified_closed_or_missing`, and `unreachable_or_unknown`. A missing sidebar entry, a stopped process, a failed `thread/list` page or an absent old ID supplied by the user is not `verified_closed_or_missing`. Locate IDs from the host registry or durable project receipts; never require the user to remember them.

Choose one operation:

| Operation | Old session | New session | Required outcome |
| --- | --- | --- | --- |
| `reuse` | Remains owner | None | Continue under the existing lease. |
| `owner_takeover` | Same canonical session, different owner | None | Rotate role lease and epoch; preserve the session ID. This is the current adapter's `takeover_role_session`. |
| `session_replace` | Retired or fenced | New canonical role session | Transfer one `role_id` and its context without reusing the old ID. |
| `commander_replace` | Retired or fenced | New canonical commander session | Rotate the project leader epoch and lease, then reconcile subordinate sessions. |
| `resume` | Host proves the stored session is recoverable | None | Recover its cursor and lease before sending more work. |

A planned change may use an authenticated old-session handoff acknowledgement. An unplanned change needs host-observed loss or closure and a lease/fencing decision. `unreachable_or_unknown` is insufficient to start a second active owner. An authorized project recovery policy may select a new session without a fresh question when identity, scope and side effects are settled. Ask only when multiple valid successors, ownership, scope or an irreversible retry decision remain genuinely open.

## When to rotate a healthy session

Evaluate at a completed task/phase boundary and after a host compaction event, without polling. Rotate only the affected role when its context degrades; replace the commander separately when its own state degrades. Do not wait for a session to become unusable, and do not rotate in the middle of an uncertain external side effect.

| Signal | Decision |
| --- | --- |
| First compaction, or measured context use reaches about 80% of the window | Prepare a concise checkpoint and successor at the next safe boundary. If the next task plus verification and checkpoint will not fit with about 20% reserve, rotate before that task. These ratios are configurable planning defaults, not a claim that 80% causes hallucinations. |
| Second compaction in the same session, or a host `ContextWindowExceeded` error | Stop assigning new work to that session and rotate at the first safe boundary. Reconcile any in-flight side effect first. |
| A verified missed user constraint, wrong project/plan, contradictory accepted state, or repeated instruction after compaction | Stop new dispatch immediately; compare against authoritative files and receipts. Rotate after a bounded successor check if context drift is implicated. If the defect comes from the plan, prompt, tool or model, fix that cause rather than copying it to a fresh session. |
| Measured input-token cost keeps rising for comparable tasks | At a phase boundary, compare expected remaining old-session input cost with a fresh session plus one-time handoff cost. Rotate only when the expected saving is material and the successor can recover the same verified state. Cumulative lifetime tokens alone are not context occupancy or proof of savings. |

Use actual host context/usage and compaction events when available (for example, Codex App Server's `thread/tokenUsage/updated` and `contextCompaction`). Do not infer context occupancy from a chat's age, sidebar appearance or cumulative lifetime token count. Without reliable numbers, use compaction events, observed errors and a small correctness check. A single compaction is a preparation signal, not automatic evidence of failure. Record the decision and its evidence in the handoff receipt, not the entire chat history.

Before activating a successor, have it identify the current goal, plan revision, permission boundary, accepted work, unresolved attempts and next authorized action from the bounded checkpoint. Compare these with project authority and receipts. If they disagree, repair the checkpoint or source conflict before switching. A successful rotation should reduce context and cost while preserving those facts; do not repeatedly create fresh sessions to mask a persistent plan or tool defect.

## Handoff transaction

1. **Discover and freeze.** Resolve project, plan revision, snapshot, current commander epoch, role, old canonical ID and permission boundary. Stop new dispatch to the old identity. Record a durable `prepared` handoff receipt before calling an external host. An old-session acknowledgement or host-observed status is a separate evidence reference.
2. **Reconcile work.** Enumerate the old session's task attempts, delivery receipts, dependencies and possible external side effects. Keep `accepted` results and their evidence. For a dispatched, running, waiting, partial or unaccepted completion claim with uncertain outcome, seal the old attempt as `unknown`, increment its cancellation generation, and investigate side effects before any retry. Do not move an attempt or an acceptance receipt to a different session. A retry uses a new attempt ID, lease, idempotency key and validation scope when required.
3. **Prepare successor.** Create or resolve the new canonical session with the same project and an authorized permission boundary. Supply a bounded checkpoint: current goal, plan/snapshot, accepted work, unresolved attempts, dependencies, constraints and evidence references. The successor must acknowledge that checkpoint. Raw chat history and a title are not an identity or checkpoint. If no durable receipts survive a reinstall, rebuild a new baseline from authoritative project files and artifacts; mark unverifiable prior outcomes `unknown`.
4. **Commit once.** Compare-and-swap the old project/role epoch and lease. Bind the new canonical ID and fresh lease, increment the relevant epoch, persist `old -> new`, checkpoint acknowledgement, host identity evidence and a `committed` receipt atomically with fencing the old owner. For commander replacement, subordinate roles remain suspended until individually rebound or replaced. If any comparison fails, do not activate the successor.
5. **Activate and clean up.** Only after commit may the successor receive new work. Late events from the old ID/epoch are retained as `stale` and cannot advance dependencies. Notify the responsible parent using the committed receipt ID. Archive an old session only after the host returns an archive receipt; a lost session is recorded as lost, not falsely archived. If notification or cleanup is uncertain, retain a recoverable pending/unknown delivery record.

The durable handoff receipt minimally contains `handoff_id`, `project_id`, `role_id` (empty for commander), `mode`, `state`, `old_session_id`, `new_session_id`, `old_epoch`, `new_epoch`, `old_lease_id`, `new_lease_id`, `plan_id`, `plan_revision`, `snapshot_id`, `permission_boundary`, `old_status_evidence_ref`, `checkpoint_ref`, `successor_ack_ref`, `in_flight_attempt_ids`, `reconciliation_refs`, `authorized_actor`, `created_at` and `committed_at`. For a context rotation, also record a concise `rotation_reason`, compaction count and any reliable usage/cost evidence references. The receipt belongs in the host's authoritative project state or another durable store that survives application reinstall. Do not place runtime receipts in the Skill directory. A receipt ID in a task packet must resolve to this record and its exact old/new binding; an arbitrary nonempty string is not proof of handoff.

The host must expose a phase-specific handoff preflight: query active/archived identity, authenticate old and new sessions, persist the prepared receipt, fence the old lease, compare-and-swap the epoch and lease, seal or reconcile attempts, deliver the checkpoint, and wake the parent. A missing operation returns `capability_gap` for the handoff phase. Do not advertise normal dispatch preflight as proof that replacement is supported.

## Failure and fallback

- If an old session is archived but recoverable, resume or explicitly replace it; do not infer loss from the UI.
- If the old session is unreachable and cannot be fenced, keep the role suspended and report `handoff_blocked`; otherwise two sessions could act at once.
- If the adapter store disappeared, old task results and dispatches are unverified. Rebuild from project files, Git/artifact evidence and host records; do not manufacture old receipts or claim an exact continuation.
- If the host lacks cross-session send, callback or wake APIs, continue the authorized work in the current chat using the project plan and report multi-session orchestration as unavailable. This is a scope reduction, not a claim that the whole project is blocked.
- If the user explicitly discards the old role/project context and all attempts are terminal, use the fresh-start retirement path. Archive the old host thread, bind a new commander or role baseline, and continue without checkpoint ACK. Do not route an intentional clean restart through `handoff_blocked`.
- A handoff completes only when the new canonical session is active under the new lease and epoch, the checkpoint is acknowledged, old ownership is fenced, and uncertain attempts are represented. `prepared`, an attempted send, or a visible new chat alone is not completion.

The isolated SQLite reference adapter implements the durable prepare/commit state machine for `session_replace` and `commander_replace`, including fencing, unknown sealing, epoch/lease CAS, and subordinate suspension. It remains transport-neutral: it does **not** create or address live Codex sessions, send the checkpoint through the host, or bind wake/send/authentication callbacks. Without those real host callbacks, the adapter returns `capability_gap`; a host must bind and test them before reporting either replacement operation as available.
