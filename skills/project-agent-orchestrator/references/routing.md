# Agent routing

## Three execution targets

### Project commander main session

There is one per project, protected by a project leadership lease and epoch. It owns project-level task selection, delegation decisions, callback validation, dependency barriers, and the decision to dispatch, wait, block, cancel, retry, or advance. It may run small work itself and may create short-lived internal children.

### Durable role main session

Create or reuse one when a responsibility is expected to recur or needs its own identity, context, lifecycle, acceptance boundary, callback endpoint, worktree, provider, permission set, or recovery path. Give it a stable `role_id` and `session_id`, bind it to exactly one project and commander epoch, and route direct callbacks to the project commander. It may create short-lived children, but it remains responsible for integrating their results.

### Ephemeral internal child

Use for a one-off or brief bounded contribution under the parent's authority: read-only exploration, a checklist, a contract comparison, a small draft, a focused test, or a single preparation step. It must have a narrow scope, a return contract, a `target_session_id`, and one parent. It should not own a project plan, acquire a commander lease, create another durable role, or send a project-level completion event.

## Promotion signals

Promote a task to a durable role main session when any material signal applies:

- the same responsibility will receive future tasks;
- the work must survive a turn, compaction, restart, or pause;
- the task has an independent acceptance or delivery contract;
- the task needs a separate context, worktree, provider, permission, or external integration;
- the task must be visible as an independently running session;
- the task owns a recurring resource or must receive direct follow-up;
- the result must callback directly to the project commander.

Keep the task internal when all of these remain true:

- it is bounded and short-lived;
- it stays under the parent task's objective and authority;
- the parent can inspect and integrate the result immediately;
- it has no independent user-facing lifecycle or callback obligation;
- it does not require a separate safety or side-effect boundary.

Task complexity is a secondary tie-breaker. A technically difficult but one-off analysis may remain a child; a simple recurring or externally risky operation may require a durable main session.

## Coordination pattern selection

The routing decision also selects a bounded coordination pattern. Keep this
metadata in the task contract so a resumed commander can reconstruct why the
next task exists:

| Pattern | Use when | Required controls |
| --- | --- | --- |
| `sequential` | One next step follows the current result. | Parent callback, dependency barrier, explicit terminal conditions. |
| `sop` | A durable role repeats a known sequence of actions. | `role_id`, `sop_id`, `sop_step`, checkpoint after each step. |
| `fan_out` | Independent bounded units can run in parallel. | `fanout_group_id`, positive `max_fanout`, one task/attempt per unit, explicit join policy. |
| `conditional` | The next branch depends on a recorded result or confidence decision. | Persisted `route_key`, immutable snapshot, one chosen branch. |
| `handoff` | Responsibility moves to a different registered session. | Authenticated target, handoff receipt, immediate-parent callback and wake receipt. |

Do not use `fan_out` to hide unbounded task creation, `conditional` to let a
worker rewrite the plan, or `handoff` to bypass acceptance. Every pattern must
declare a terminal or cancellation route; `max_attempts`, lease expiry and
`unknown` sealing are safety limits rather than substitutes for a project
decision.

## Decision order

1. Resolve project, plan, snapshot and authority.
2. Ask who owns the result and who must validate it.
3. Ask whether the responsibility persists beyond the current bounded task.
4. Check context, tool, permission, worktree, provider, recovery and side-effect boundaries.
5. Check independent acceptance, visibility, callback and dependency-barrier requirements.
6. Use complexity, parallelism, latency and cost as secondary factors.
7. If low-risk and still ambiguous, choose an internal child. If stateful, side-effecting, long-running, recovery-sensitive or independently callback-visible, choose a durable main session.

## Existing durable role sessions

Before creating a durable role main session, the host must list compatible
sessions for the same `project_id` and `role_id`. Compatibility includes the
plan/snapshot boundary, permission boundary, lifecycle state, commander epoch,
and the role's health/recovery status. A display name, idle state, process ID,
or a similar title is not enough to identify a candidate.

When one or more compatible candidates exist, the commander must resolve the
session explicitly:

| Resolution | Meaning | Required evidence |
| --- | --- | --- |
| `reuse` | Continue the selected session with its current owner and role epoch. | Candidate ID and a current-session check. |
| `takeover` | Transfer ownership of the selected **same** session to the requesting commander or role owner. | Authorized decision, old lease check, new lease, incremented `role_epoch`, and a handoff receipt. |
| `new` | Create a separate durable role session. | Explicit user/authority decision when a compatible candidate exists; otherwise an empty candidate list is sufficient. |

If a compatible candidate exists and neither the current request nor an
authorized project rule chooses a resolution, return `session_resolution_pending` with the candidate IDs. Do
not silently create a duplicate role session or silently take over an active
one. A `takeover` must fail closed when the expected old epoch or lease no
longer matches; the commander should rediscover candidates and ask only if the
new evidence leaves the choice open. Replacing the session itself, including
the project commander, follows [handoff-recovery.md](handoff-recovery.md),
not this same-session `takeover` operation.

The resolution is part of the task contract and callback evidence. A reused
session keeps its `role_epoch`; a takeover records
`previous_owner_session_id` and `handoff_receipt_id`; a new session records
`candidate_session_ids` and the newly allocated epoch. A later callback from a
superseded epoch is stale and cannot advance the plan.

## Completion and acceptance ownership

The worker's `task.completed_claim` is a bounded completion claim. It tells the
parent that the worker has exhausted the authorized scope and submitted its
deliverables; it does not grant acceptance. A durable role session remains
available after that attempt and may receive a correction attempt or a later
task.

Create an independent acceptance role only when its evidence, permissions,
context, or responsibility differs materially from the worker's self-check.
When it is needed, set `acceptance_mode=independent_validator`, bind
`acceptance_authority_session_id` to the registered validator, and give it one
`acceptance_scope_id`. The validator emits one validation receipt and the
single `accepted`/`rejected` decision for the worker's attempt; the commander
uses that decision to advance the plan instead of redoing the domain checks.
If the validator would only repeat the worker's tests, use a
commander gate or an ephemeral check instead.

## Parent-child and graph invariants

The adapter must reject a dispatch before recording it when any of these holds:

- the target is missing, the parent is missing, or `target_session_id == parent_session_id`;
- the child has more than one parent, the proposed parent is in `ancestor_session_ids`, or `dispatch_depth` exceeds the configured bound;
- `project_id`, `plan_id`, `snapshot_id`, `root_session_id` or commander epoch differs from the active parent;
- a durable role is reused under another project, role identity or permission boundary;
- the target would create a second commander lease for the same project;
- a dependency cycle or an impossible `join_policy` is introduced.

Every child has exactly one immediate parent. A child returns evidence to that parent; it does not bypass the parent to advance a plan. A durable role main session returns a validated task receipt to the project commander. A commander advances a dependency barrier only after every required task receipt is `accepted` or the plan explicitly allows a bounded partial result. A proposed dispatch that violates these rules returns `cycle_detected`, `multiple_parent`, `commander_conflict`, `plan_drift` or `target_unresolved` and has no dispatch side effect.
