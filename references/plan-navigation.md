# Read-Only Plan Navigation

Use this adapter only when the project already has an active, exclusive root `PLANS.md` that follows the optional navigation contract defined by `bootstrap-codex-project`. Do not create navigation merely because durable-context is active.

## Authority

- The user's latest instruction remains first.
- Root `PLANS.md` remains the only plan authority when it is active and exclusive.
- The durable ledger remains the current requirements and checkpoint authority.
- `current_task_id`, the one `in_progress` milestone, and `on_complete` retain machine execution semantics.
- Route coordinates are read-only position labels. Durable-context may validate and project them but never infer, advance, repair, or write them.

## Accepted Envelope

Accept only positive-integer coordinates in this form:

```text
R<route>:A<stage>[/B<branch>][/C<continuity-work>]
```

Require `route_id` and `current_route_coordinate`, an active and exclusive plan, exactly one `in_progress` milestone matching `current_task_id`, and an exact route-ID match. When the Milestones table has a `Route coordinate` column, require the current row to match the current coordinate and reject invalid, duplicate, or cross-route coordinates.

For a `C` coordinate, also require:

- `latest_change_class: priority_branch`
- a named `continuity_parent_task_id`
- the parent milestone to be `deferred` or `blocked`
- `on_complete: resume:<continuity-parent-task-id>`

Reject a continuity parent on an `A` or `A/B` coordinate. Never accept a coordinate as an `on_complete` target.

## Fail-Closed Projection

If navigation is absent, preserve legacy resume, MCP, and Obsidian behavior. If it is configured but invalid, report bounded validation errors without returning a trusted coordinate. Do not guess a replacement from the ledger, handoff, conversation, task names, or source tree.

When valid:

- add a compact `Plan Navigation` section to resume output;
- allow the read-only Context MCP to return and search the verified coordinate;
- include the validation state in health and project-list output;
- project the coordinate and source-file hash to Obsidian as non-authoritative metadata.

The source hash proves which `PLANS.md` bytes were inspected. It does not prove that the implementation is correct or that the plan remains current after the read.

## Change Boundary

Route updates belong to the plan owner, normally `bootstrap-codex-project` or an explicit human edit. Durable-context must not add a database, write-capable MCP tool, background writer, Hook semantic inference, or a second task graph to maintain these coordinates.
