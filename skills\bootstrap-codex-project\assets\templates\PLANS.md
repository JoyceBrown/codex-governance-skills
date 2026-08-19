# Active Execution Plan

plan_id: {{PLAN_ID}}
status: active
authority: exclusive
current_task_id: {{CURRENT_TASK_ID}}
continuation_policy: validate_then_advance
completion_policy: all_required_items
priority_basis: {{USER_OUTCOME_OR_VERIFIED_PREREQUISITE}}
delivery_contract: {{NONE_OR_REQUIRED_ARTIFACT_AND_REPOSITORY_EVIDENCE}}
roadmap_reference: {{ROADMAP_MILESTONE_OR_NONE}}
latest_change_id: {{CHANGE_ID}}
latest_change_class: {{TASK_ADJUSTMENT_PRIORITY_BRANCH_OR_ROADMAP_CHANGE}}
change_authority_reference: {{DURABLE_DOCUMENT_DECISION_OR_NONE}}
delegated_execution: {{NONE_OR_ACTIVE_DELEGATION_IDS}}
on_complete: {{WAIT_OR_RESUME_TASK_OR_ACTIVATE_PLAN}}

When plan navigation is justified, add these metadata fields above and remove this paragraph after adapting the template:

```text
route_id: {{ROUTE_ID}}
current_route_coordinate: {{CURRENT_ROUTE_COORDINATE}}
continuity_parent_task_id: {{PARENT_TASK_ID_OR_NONE}}
```

Keep task IDs and route coordinates separate. `on_complete` must continue to target a task or plan ID, never an `R#:A#/B#/C#` coordinate.

Use this plan only for work that spans multiple modules, has meaningful risk, must survive a context reset, or needs explicit protection from competing plans. Remove this file when the project does not need a durable active plan.

## Objective

{{ONE_MEASURABLE_OUTCOME}}

## Priority and completion contract

{{WHY_THIS_IS_THE_HIGHEST_VALUE_AUTHORIZED_WORK}}

{{BUNDLED_REQUIREMENTS_OR_NAMED_FINISH_BOUNDARY_THAT_MUST_COMPLETE_AS_ONE_UNIT}}

A bare continuation request validates the current task first, finishes missing
acceptance criteria, and otherwise advances only to the next authorized
milestone. Partial completion of a required bundle is progress, not completion.

## Authoritative context

{{ONLY_THE_FILES_CONSTRAINTS_AND_PRIOR_DECISIONS_NEEDED}}

## Allowed scope

{{WORK_THIS_PLAN_AUTHORIZES}}

## Excluded scope

{{WORK_THIS_PLAN_MUST_NOT_START}}

## Deferred work

| Item | Reason deferred | Impact | Resume condition |
| --- | --- | --- | --- |
| {{TASK_OR_MILESTONE}} | {{REASON}} | {{DEPENDENCY_SCHEDULE_OR_SCOPE_EFFECT}} | {{CONDITION}} |

## Milestones

| Task ID | Status | Route coordinate | Verifiable outcome |
| --- | --- | --- | --- |
| {{CURRENT_TASK_ID}} | in_progress | {{ROUTE_COORDINATE_OR_NONE}} | {{OUTCOME}} |

Use only `pending`, `in_progress`, `blocked`, `deferred`, or `completed` for task status. Keep exactly one `in_progress` task and make it match `current_task_id`. Represent bounded parallel help in delegation packets, not as competing current plan authority.

## Risks and recovery

{{FAILURE_MODES_COMPATIBILITY_AND_RECOVERY}}

## Validation

{{COMMANDS_AND_OBSERVABLE_ACCEPTANCE_CRITERIA}}

## Validation evidence

{{RESULTS_EXIT_CODES_SCREENSHOTS_DIFFS_OR_OTHER_EVIDENCE}}

## Delivery state

{{ARTIFACT_VERSION_PATH_DIGEST_VALIDATION_WORKTREE_COMMIT_PUSH_DEPLOYMENT_AND_KNOWN_LIMITS_OR_NONE}}

## Decision log

{{DECISIONS_THAT_CHANGED_PRIORITY_SCOPE_OR_SEQUENCE}}

## Requirement change log

| Change ID | Class | User intent | Authority updated | Previous work | Resume behavior |
| --- | --- | --- | --- | --- | --- |
| {{CHANGE_ID}} | {{CLASS}} | {{PLAIN_LANGUAGE_REQUEST}} | {{CURRENT_TASK_PLAN_OR_DURABLE_DOCUMENT}} | {{DEFERRED_TASK_OR_NONE}} | {{WAIT_RESUME_OR_ACTIVATE}} |

## Active delegations

{{DELEGATION_IDS_BOUNDED_SCOPES_AND_STATUS_OR_NONE}}
