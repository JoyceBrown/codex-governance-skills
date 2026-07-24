# Active Execution Plan

plan_id: {{PLAN_ID}}
status: active
authority: exclusive
current_task_id: {{CURRENT_TASK_ID}}
roadmap_reference: {{ROADMAP_MILESTONE_OR_NONE}}
latest_change_id: {{CHANGE_ID}}
latest_change_class: {{TASK_ADJUSTMENT_PRIORITY_BRANCH_OR_ROADMAP_CHANGE}}
change_authority_reference: {{DURABLE_DOCUMENT_DECISION_OR_NONE}}
delegated_execution: {{NONE_OR_ACTIVE_DELEGATION_IDS}}
on_complete: {{WAIT_OR_RESUME_TASK_OR_ACTIVATE_PLAN}}

Use this plan only for work that spans multiple modules, has meaningful risk, must survive a context reset, or needs explicit protection from competing plans. Remove this file when the project does not need a durable active plan.

## Objective

{{ONE_MEASURABLE_OUTCOME}}

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

| Task ID | Status | Verifiable outcome |
| --- | --- | --- |
| {{CURRENT_TASK_ID}} | in_progress | {{OUTCOME}} |

Use only `pending`, `in_progress`, `blocked`, or `completed` for task status. Keep exactly one `in_progress` task unless the plan explicitly supports independent parallel work.

## Risks and recovery

{{FAILURE_MODES_COMPATIBILITY_AND_RECOVERY}}

## Validation

{{COMMANDS_AND_OBSERVABLE_ACCEPTANCE_CRITERIA}}

## Validation evidence

{{RESULTS_EXIT_CODES_SCREENSHOTS_DIFFS_OR_OTHER_EVIDENCE}}

## Decision log

{{DECISIONS_THAT_CHANGED_PRIORITY_SCOPE_OR_SEQUENCE}}

## Requirement change log

| Change ID | Class | User intent | Authority updated | Previous work | Resume behavior |
| --- | --- | --- | --- | --- | --- |
| {{CHANGE_ID}} | {{CLASS}} | {{PLAIN_LANGUAGE_REQUEST}} | {{CURRENT_TASK_PLAN_OR_DURABLE_DOCUMENT}} | {{DEFERRED_TASK_OR_NONE}} | {{WAIT_RESUME_OR_ACTIVATE}} |

## Active delegations

{{DELEGATION_IDS_BOUNDED_SCOPES_AND_STATUS_OR_NONE}}
