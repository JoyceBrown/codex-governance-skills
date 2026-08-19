# Plan navigation

Use this optional extension only when a long-running project repeatedly loses its position inside a multi-stage route, temporary priority branches obscure the work to resume, or a context reset has caused route drift. Do not add it to an ordinary short or flat plan.

## Contents

- [Authority boundary](#authority-boundary)
- [Coordinate grammar](#coordinate-grammar)
- [Optional active-plan fields](#optional-active-plan-fields)
- [Single-focus rule](#single-focus-rule)
- [Change mapping](#change-mapping)
- [Resume and drift handling](#resume-and-drift-handling)
- [Stable identifiers](#stable-identifiers)
- [Validation target](#validation-target)

## Authority boundary

Route coordinates annotate the active plan; they never authorize work.

- The user's latest explicit instruction controls the current request.
- An active, exclusive root `PLANS.md` remains the only repository execution plan.
- `current_task_id` remains the single current task and must match the one `in_progress` milestone.
- `on_complete` remains the machine-readable continuation action.
- Repository files, tests, runtime evidence, and durable decisions remain authoritative for implementation truth.
- A coordinate is invalid when it disagrees with the active plan. Never repair that disagreement by trusting the coordinate.

## Coordinate grammar

Use this bounded form:

```text
R<route>:A<stage>[/B<branch>][/C<continuity-work>]
```

Examples:

```text
R7:A3
R7:A3/B2
R7:A3/B2/C1
```

Each number is a positive integer without leading signs. Use:

- `A` for an approved long-horizon stage.
- `B` for a persistent work branch inside the current stage.
- `C` only for accepted temporary work that interrupts another task and must return to it.

Treat the parent as a continuity parent: where execution was interrupted and where it should normally return. Do not choose a parent merely because its topic or code area looks similar.

## Optional active-plan fields

Enable navigation only when both fields are present:

```text
route_id: R7
current_route_coordinate: R7:A3/B2
```

For temporary continuity work, also record:

```text
current_task_id: login-fix
current_route_coordinate: R7:A3/B2/C1
continuity_parent_task_id: android-session-recovery
latest_change_class: priority_branch
on_complete: resume:android-session-recovery
```

Keep task IDs and coordinates separate. Task IDs are machine continuation targets; coordinates are navigation labels. Never put a coordinate containing `:` or `/` into `on_complete`.

When a Milestones table includes a `Route coordinate` column, its current task row must match `current_route_coordinate`. Coordinates in that column must be valid, unique, and use the active `route_id`. Use `none` for a task that has no justified coordinate.

## Single-focus rule

Keep exactly one milestone `in_progress`. A route may describe many planned branches, and bounded delegated work may run concurrently, but neither creates another current execution authority.

For an active `C` coordinate:

- the continuity parent must remain in Milestones with `deferred` or `blocked` status;
- the current task remains the one `in_progress` milestone;
- `on_complete` must be `resume:<continuity-parent-task-id>`;
- the latest change class must be `priority_branch`.

After the temporary task completes, restore the parent task as `current_task_id`, restore its `A/B` coordinate, clear `continuity_parent_task_id`, and preserve the branch in the existing change log or checkpoint evidence.

## Change mapping

- `task_adjustment`: keep the coordinate unless the accepted work actually moves to another persistent branch.
- `priority_branch`: create `C` only when the interruption survives the current turn or needs an explicit return target. Ordinary bounded edits do not get a `C` node.
- `roadmap_change`: update the durable product, architecture, compatibility, safety, or decision owner first. If the approved long-horizon route is replaced, keep the old route ID historical and start a new route ID.

Do not create coordinates for discussion, proposals, observations, rejected ideas, single tool calls, tests, or cosmetic edits that close in the current turn.

## Resume and drift handling

When the user says only "continue":

1. Validate the active plan and its single current task.
2. Validate the optional coordinate envelope.
3. If a valid `C` is active, finish it and follow its exact `on_complete` action.
4. Otherwise continue the task at the verified `A` or `A/B` coordinate.
5. Advance to another `A` only after the current stage's actual exit conditions pass.

If navigation metadata is missing, malformed, stale, or inconsistent, ignore it and reconcile `PLANS.md`; do not guess from recent conversation.

## Stable identifiers

Coordinates are addresses. Do not renumber historical `A`, `B`, or `C` segments merely because descriptions or local details changed. Append new coordinates under the existing route. Create a new route ID only when an approved route is genuinely replaced, and mark the old route or plan superseded rather than changing the meaning of its old addresses.

## Validation target

Verify that navigation:

- is optional and does not burden short plans;
- cannot create a second active task;
- fails closed on malformed or route-mismatched coordinates;
- cannot resume a task other than the declared continuity parent;
- survives context reset without replacing task IDs or plan authority;
- does not create nodes for routine local work.
