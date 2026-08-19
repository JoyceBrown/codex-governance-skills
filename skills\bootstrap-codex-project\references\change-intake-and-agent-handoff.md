# Requirement changes and agent handoff

Use this module when the user changes a requirement during ongoing work, when work moves to a new Codex task or fork, or when the main agent delegates part of the active task to a subagent.

The user should not need to name a planning class. Infer the class from the effect of the request, then ask at most one plain-language question if the answer materially changes the result.

## Classify the requirement by effect

Use exactly one canonical class for the latest material change:

| Class | Plain meaning | Typical effect | Authority update |
| --- | --- | --- | --- |
| `task_adjustment` | Change how the current task is done | Implementation detail, copy, layout, or acceptance detail stays inside the current objective and durable boundaries | Update the current task and acceptance criteria; update only an existing or justified checkpoint; do not change the roadmap |
| `priority_branch` | Do something else first, then stop or return | Current work is paused or superseded temporarily, but the project destination remains unchanged | Update `PLANS.md`; record deferred work, reason, impact, resume condition, and exact `on_complete` behavior |
| `roadmap_change` | Change what the project is becoming | Durable scope, non-goals, architecture, safety, data compatibility, supported platforms, or long-term destination changes | Update only the existing or justified durable owners actually affected; update a roadmap only when the project has one, then reconcile `PLANS.md` when planning authority is enabled |

When the optional plan-navigation extension is enabled, map these classes without creating new authority semantics:

- Keep the current route coordinate for a `task_adjustment` unless the accepted work actually changes persistent branch.
- Represent a `priority_branch` as `C` only when it interrupts work beyond the current turn or requires an explicit return target. Keep the paused task as `continuity_parent_task_id`, and keep `on_complete` as `resume:<task-id>`.
- Start a new route ID for a `roadmap_change` only when an approved long-horizon route is genuinely replaced. Preserve the old route ID as historical.

Read `plan-navigation.md` before adding or changing these optional fields.

Classify the real effect, not individual words. "Temporarily" does not make an incompatible database migration a harmless branch. "Small change" does not make a new data-sharing boundary a task adjustment.

Never silently downgrade a `roadmap_change` to `task_adjustment`. A request can contain several edits; use the highest consequential class that applies, or split it into separately identified changes when their owners and timing differ.

## Ask only when the answer matters

Ask one question when any of these remains ambiguous:

- whether Codex should return to the paused task afterward
- whether the request replaces a durable product or architecture decision
- whether the new work belongs inside the current objective or becomes the new priority
- whether the user wants an ordinary bounded subagent assignment or a formal new-task takeover with responsibility transfer
- whether a consequential domain term has a project-specific meaning that
  changes architecture, configuration, data, safety, or acceptance

Prefer plain language:

- "Is this only changing how the current task is done, or does it replace a long-term product decision?"
- "After this is finished, should Codex return to the paused task or stop for your review?"
- "Should this be part of the current task, or should it become the new thing Codex finishes first?"

For reversible local ambiguity, state a low-risk assumption and continue. Ask instead of assuming when the choice affects architecture, safety, data compatibility, external actions, destructive behavior, or restoration of paused work.

When terminology changes the result, derive its meaning from authoritative
project evidence or ask one plain-language question, then record the accepted
meaning in the glossary or owning domain document. Do not ask about harmless
wording differences.

## Record the change

When planning authority is enabled, every material change to active work should receive a stable change ID and be recorded in `PLANS.md`:

```text
latest_change_id: CHANGE-004
latest_change_class: priority_branch
change_authority_reference: none
```

For `roadmap_change`, `change_authority_reference` must point to the durable document or decision record that now owns the change. For the other two classes, use `none` unless a durable document genuinely changed.

If cross-task checkpointing is already enabled or now justified, update `docs/work/current.md` with the classification, user decision, evidence gathered, and exact next action. Do not create a checkpoint merely for a small local adjustment. A checkpoint records the result; it does not become a second plan.

## New task, reset, and fork

Durable repository context and conversation context are different:

- A new task or context reset in the same repository discovers applicable `AGENTS.md` files again, but it does not inherit the previous conversation transcript.
- A fork copies the current conversation at the point of the fork, but later changes in either branch are independent.
- Repository facts, active authority, exclusions, latest decisions, and checkpoint evidence must therefore live in repository artifacts when they need to survive a task boundary.

Use this recovery order in a new task:

1. Read applicable `AGENTS.md` files from the repository root to the working directory.
2. If planning authority is enabled, read active `PLANS.md` before selecting work.
3. Read `docs/work/current.md` for evidence and the next action, never as independent authority.
4. Read only the product, architecture, decision, and code files referenced by the active plan.
5. Reconcile any new user instruction using the classification rules above.

Do not claim that every rule follows automatically. Applicable `AGENTS.md` guidance is durable and automatically discovered only when the task is opened in the correct repository, worktree, and working directory. A closer `AGENTS.md` or `AGENTS.override.md` may change the effective rules. The old transcript and unrecorded decisions are not inherited.

## Resolve the destination before task creation

When the user refers to a named new task, existing task, project task, or
handoff destination, resolve it before creating anything:

1. identify the intended project and environment;
2. inspect existing tasks when the wording may refer to one already created;
3. match the explicit name, project, path, and responsibility;
4. create a task only when the user requested creation and no intended
   existing destination matches; and
5. confirm that the created or selected task is readable before sending the
   formal handoff or reporting success.

If creation returns an identifier that is not yet readable, reconcile that
state before creating a fallback. Never create two active destinations for the
same takeover merely because the first confirmation failed.

## Verify capability blockers

Before telling the user that a new or resumed task lacks a terminal, editor,
repository, version-control tool, dependency, permission, or runtime
capability, inspect the current workspace and callable tools and perform a safe
discovery probe. Distinguish:

- a genuinely unavailable capability;
- one failed invocation;
- stale conversation or handoff context;
- a missing dependency that may or may not be installable within authority;
- an approval or side-effect boundary; and
- an external or environment failure.

Record concrete evidence and the smallest required user or external action.
Capability verification does not grant new permission.

## Formal handoff to a new task

When a new Codex task will formally continue or take over the work, do not rely on repository discovery alone. Provide a short handoff message and ensure durable state is current. Include:

```text
repository_root and worktree
target task identity and how it was resolved
branch and base revision
working-tree state and user changes that must be preserved
concurrent tasks, worktrees, branches, and overlapping edit scopes
active plan and current task ID
latest user decision and requirement-change class
current objective and observable acceptance criteria
authoritative files and excluded scope
exact next action and validation still required
verified capabilities, attempted failures, and changed strategy
artifact, repository, and delivery state when relevant
external and destructive side-effects policy
responsibility: assist, continue, or take over
integration and final-report owner
```

Use `assets/templates/new-task-handoff.md` as a drafting aid when the state cannot be stated safely in one short message. A task marked `assist` returns evidence to the originating task. A task marked `continue` advances the same active task without taking final ownership. A task marked `take_over` becomes responsible for integration, user reporting, and the user-request completion claim. Project completion remains a separate claim and requires project-level acceptance criteria.

Before handoff, record unresolved work and evidence in `docs/work/current.md` when checkpointing is enabled. If different tasks use different worktrees, never describe them as sharing live files. If they use the same worktree, disclose concurrent edits and coordinate write scopes.

## Main agent and subagent authority

The main agent interprets the user's instruction, maintains the active plan within that authority, defines delegation boundaries, and owns integration and final validation for the current user request unless a formal task handoff transfers that responsibility. The user and authoritative project decisions control durable direction; `PLANS.md` is the repository execution authority when active. An agent does not own either source and may not enlarge them on its own.

A subagent may implement or investigate only the bounded task it receives. It must not independently:

- change `docs/roadmap.md` or durable product direction
- change active-plan authority or `on_complete`
- reclassify a user requirement
- broaden allowed scope or remove exclusions
- select unrelated roadmap work
- claim that the overall user request or project is complete

These powers are not transferable through an ordinary subagent packet. A subagent may be asked to analyze alternatives or propose a change, but the main agent must reconcile the proposal with the user's authority and update durable owners itself. A formal new-task takeover uses the handoff contract above, not a subagent packet.

## Delegation packet

Do not rely on a subagent to reconstruct the current task from repository files alone. Send a bounded packet containing:

```text
task_id
objective
requirement_change_class
allowed_scope
excluded_scope
authoritative_files
acceptance_criteria
validation
write_policy
repository_state
side_effects_policy
escalation
expected_return
```

Use `assets/templates/agent-task-packet.md` as a drafting aid when needed. The packet is task-local context, not a second source of execution authority. It may narrow the active plan but must not broaden it.

The packet must comply with explicit user instructions, applicable `AGENTS.md`, and active `PLANS.md`; it may only narrow their allowed scope. If a higher source clearly narrows the packet, follow the narrower rule. If sources conflict materially, appear to broaden active authority, or completion requires leaving scope, the subagent must stop and return the conflict or blocker instead of choosing an interpretation.

The side-effects policy must explicitly permit or deny dependency installation, network calls, external-system changes, database mutations, commits, pushes, deployments, and destructive operations as relevant. Unmentioned external or destructive effects are denied.

For parallel work, prefer independent read-heavy investigations or disjoint write scopes. Agents in the same worktree share live files, so the main agent must prevent overlapping edits or explicitly coordinate them. Agents in separate worktrees do not share live edits and require an explicit integration path.

## Integration and completion

When a subagent returns, the main agent must:

1. Compare the result with the packet and active plan.
2. Inspect the actual diff or evidence; do not accept a completion claim on wording alone.
3. Run or verify the required checks at the integration boundary.
4. Resolve conflicts without discarding unrelated user changes.
5. Update the checkpoint and plan status.
6. Distinguish completion levels: delegated subtask, current feature, active plan, current user request, and whole project.
7. Claim current-user-request completion only when that request's acceptance criteria are satisfied; claim project completion only against separate project-level criteria.

Subagent success means its bounded assignment is ready for integration. It does not mean the active plan or user request is complete.
