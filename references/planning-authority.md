# Planning authority

Use this module only when a project has long-running work, competing plans, cross-session state, or a demonstrated tendency to execute the wrong plan.

## Contents

- [Outcome](#outcome)
- [Plain-language discovery](#plain-language-discovery)
- [Authority model](#authority-model)
- [Artifact ownership](#artifact-ownership)
- [Active plan contract](#active-plan-contract)
- [Optional plan navigation](#optional-plan-navigation)
- [Continuation, completion, and delivery](#continuation-completion-and-delivery)
- [Reprioritization](#reprioritization)
- [Mid-project requirement changes](#mid-project-requirement-changes)
- [Existing repository migration](#existing-repository-migration)
- [AGENTS.md contract](#agentsmd-contract)
- [Validation](#validation)

## Outcome

At any moment, a project may contain many sources of direction but at most one source with current execution authority.

Do not ask the user to design this model. Infer it from the repository and obtain only the product decisions that cannot be derived safely.

## Plain-language discovery

Ask only questions that change the generated result. Prefer wording such as:

1. What do you want Codex to finish first right now?
2. When that work is done, should Codex stop for review, return to a named earlier task, or start another named task?
3. Which areas should Codex leave alone for now?

Translate the answers into plan metadata, allowed scope, excluded scope, deferred work, and completion behavior. Do not require the user to know terms such as execution authority, plan ID, checkpoint, or roadmap.

## Authority model

Apply this precedence inside the project context system:

1. The user's latest explicit instruction controls the current request.
2. `PLANS.md` controls ongoing work only when it is marked `status: active` and `authority: exclusive`.
3. `docs/roadmap.md`, `docs/work/current.md`, README files, archived plans, and todo lists provide context but cannot independently authorize work.

Project boundaries, architecture, safety, and data constraints remain authoritative even when the user changes task priority. If a reprioritization would change one of those boundaries, surface the impact instead of treating it as an ordinary reorder.

## Artifact ownership

### `docs/roadmap.md`

Owns long-term outcomes, milestone relationships, dependencies, and sequencing rationale.

It must declare:

```text
execution_authority: none
```

Prefer outcome-oriented milestones over unchecked task lists. Never label a roadmap item as the current task unless the active plan explicitly references it.

### `PLANS.md`

Owns the one active long-running execution plan. It names the current task, allowed and excluded scope, deferred work, validation, and completion behavior.

When no plan is active, use `status: paused`, `completed`, `superseded`, or `archived` and `authority: none`.

### `docs/work/current.md`

Owns transient progress and handoff state: completed work, evidence, failures, blockers, decisions, and the exact next action inside the active plan.

It must declare:

```text
record_kind: checkpoint
execution_authority: none
```

It may point to `PLANS.md`; it must not invent or select a task outside that plan.

### `AGENTS.md`

Owns the durable routing and conflict rules that Codex must load in every session. Keep this section short and link to the authoritative files.

## Active plan contract

An active plan must include:

```text
plan_id
status: active
authority: exclusive
current_task_id
continuation_policy: validate_then_advance
completion_policy: all_required_items
priority_basis
delivery_contract
latest_change_id
latest_change_class
change_authority_reference
on_complete
```

It must also state:

- one measurable objective
- authoritative context and constraints
- allowed scope
- explicitly excluded scope
- deferred work and its resume condition
- ordered milestones with stable task IDs and statuses
- risks and recovery options
- validation commands and observable acceptance criteria
- validation evidence gathered so far
- decisions that changed the plan

Declare each metadata field once. Conflicting duplicate values are invalid. Keep exactly one milestone `in_progress`, and make its task ID equal `current_task_id`; delegated parallel work remains subordinate to that current task.

`priority_basis` states why the current task is the highest-value authorized
work. `delivery_contract` is `none` when no artifact or external state belongs
to the objective; otherwise it names the evidence required for delivery
closure. Do not interpret it as authority to commit, push, publish, deploy, or
mutate an external system.

Allowed `on_complete` forms:

```text
wait
resume:<task-id>
activate:<plan-id>
```

Avoid ambiguous values such as `continue`, `return to the plan`, or `do the next task`.

## Optional plan navigation

Use `references/plan-navigation.md` only when a multi-stage route has demonstrated navigation drift, temporary priority branches need an explicit continuity parent, or work must recover its structural position after context resets. Do not enable it merely because a plan is long.

Plan navigation adds optional `route_id`, `current_route_coordinate`, and, for temporary continuity work, `continuity_parent_task_id`. These fields annotate the active plan and never replace `plan_id`, `current_task_id`, milestone status, `latest_change_class`, deferred work, or `on_complete`.

Keep one `in_progress` milestone. A `C` coordinate is the navigation expression of an accepted `priority_branch`; its parent task remains paused and its `on_complete` value resumes that task ID. Do not put the route coordinate itself in `on_complete`.

## Continuation, completion, and delivery

For an active long-running plan, use
`continuation_policy: validate_then_advance`. A bare "continue" means:

1. validate the current task against all acceptance criteria;
2. finish the highest-value missing criterion when incomplete;
3. otherwise complete the task and advance to the next authorized pending
   milestone; and
4. follow `on_complete` only after the plan's completion boundary is met.

Use `completion_policy: all_required_items`. When the user explicitly bundles
several requirements or names a finish-before-stop boundary, treat the bundle
as one completion unit. Partial results are progress, not completion.

Record the user-visible outcome in the priority basis. Internal cleanup may
lead only when evidence shows it is a prerequisite or a higher safety,
architecture, or data boundary requires it.

When delivery produces an artifact or external state, define the report
contract in advance: relevant version, artifact identity or location,
validation, known limits, working-tree state, commit/push/publication state,
and recovery evidence. Reporting a state does not authorize changing it.

Read `execution-discipline.md` for retry, blocker, terminology,
effective-state, and blast-radius rules. These rules never authorize work
outside the active plan.

## Reprioritization

Treat a temporary focus change as a priority override, not an automatic change to the long-term destination.

Record:

- the new current task
- the previous task or milestone being deferred
- why the priority changed
- dependencies and schedule effects
- the condition for resuming deferred work
- whether product or architecture boundaries changed
- the exact `on_complete` action

Do not delete deferred tasks or mark them complete. Do not resume them merely because the current task became difficult.

## Mid-project requirement changes

Read `change-intake-and-agent-handoff.md` when the user changes a requirement during active work. Classify the effect as `task_adjustment`, `priority_branch`, or `roadmap_change`; the user does not need to know these labels.

- A `task_adjustment` updates the current task and its acceptance criteria without changing roadmap authority.
- A `priority_branch` updates `PLANS.md`, preserves deferred work, and states the resume condition and exact `on_complete` action.
- A `roadmap_change` first updates its durable owner, such as product, architecture, compatibility, safety, or a decision record, then reconciles the active plan.

Record `latest_change_id`, `latest_change_class`, and `change_authority_reference` in an active plan. Never interpret a wording cue such as "temporarily" as stronger evidence than the actual product or technical effect.

## Existing repository migration

When several files appear actionable:

1. Inventory roadmap, plan, todo, status, issue, and handoff files.
2. Preserve human-authored intent and history.
3. Identify which work the user actually wants active now.
4. Assign long-term outcomes to the roadmap.
5. Assign current authorized work to `PLANS.md`.
6. Assign progress evidence to `docs/work/current.md`.
7. Mark obsolete plans `completed`, `superseded`, or `archived` instead of deleting them without consent.
8. Remove duplicated task lists or replace them with links to the canonical owner.
9. Add the authority contract to root `AGENTS.md`.
10. Validate links, metadata, and active-plan count.

If the current work cannot be inferred safely, ask the first plain-language discovery question and continue after the answer.

## AGENTS.md contract

Adapt this contract to the repository language and paths:

```md
## Plan authority

- The user's latest explicit instruction controls the current request.
- `PLANS.md` is the only repository plan that may authorize ongoing work when it is marked active and exclusive.
- `docs/roadmap.md` describes direction and never authorizes work by itself.
- `docs/work/current.md` records progress and never creates a new task.
- Do not select work from README files, roadmaps, archived plans, or todo lists unless the active plan references it.
- If the current task is blocked, diagnose it or report the blocker; do not switch to an unauthorized roadmap task.
- On completion, follow the active plan's exact `on_complete` value.
- Interpret a bare continue by validating the current task, finishing missing
  acceptance criteria, and then advancing only to the next authorized
  milestone.
- Treat explicitly bundled requirements as one completion unit; partial
  progress is not completion.
- Do not repeat a failed approach without new evidence or a changed strategy,
  and verify current capabilities before declaring a blocker.
- When the plan has a delivery contract, report its artifact, validation, and
  repository or external-state evidence without assuming authority to mutate
  that state.
- Classify a material mid-project change before editing plan authority: use `task_adjustment`, `priority_branch`, or `roadmap_change` as defined by the project context system.
- The main agent interprets user changes, maintains the plan within the user's authority, and owns integration for the current request. Subagents receive bounded task packets and may not broaden scope or select roadmap work.
```

Do not add this section when the project has no planning-authority module.

## Validation

Verify:

- no more than one plan is active with exclusive authority
- every active plan has all required metadata
- the current task belongs to the active plan's milestones or allowed scope
- roadmap and checkpoint files explicitly have no execution authority
- root `AGENTS.md` routes execution to the active plan
- `on_complete` is explicit and machine-readable
- optional plan-navigation fields are internally consistent and never create another current task
- continuation and completion policies are explicit and use
  `validate_then_advance` and `all_required_items`
- priority basis names the user outcome or demonstrated prerequisite
- delivery contract is explicit, including `none` when no artifact or external
  state belongs to the objective
- deferred work has not been silently deleted or marked complete
- roadmap checkboxes cannot be mistaken for current task authorization
- the latest material requirement change has a canonical class and stable change ID
- a roadmap change references the durable document or decision that owns it
- root `AGENTS.md` limits subagents to explicitly delegated scope
- project tests and plan-specific acceptance checks remain separate from context validation
