# Agent Task Packet

This packet narrows work delegated by the main agent. It does not replace or broaden the active plan, and it does not grant roadmap, current-user-request completion, or whole-project completion authority.

task_id: {{TASK_ID}}
objective: {{BOUNDED_OBJECTIVE}}
requirement_change_class: {{TASK_ADJUSTMENT_PRIORITY_BRANCH_OR_ROADMAP_CHANGE}}

## Allowed scope

{{FILES_BEHAVIORS_AND_DECISIONS_THE_AGENT_MAY_TOUCH}}

## Excluded scope

{{FILES_BEHAVIORS_AND_AUTHORITIES_THE_AGENT_MUST_NOT_TOUCH}}

## Authoritative files

{{MINIMUM_FILES_THE_AGENT_MUST_READ}}

## Acceptance criteria

{{OBSERVABLE_BOUNDED_OUTCOMES}}

## Validation

{{CHECKS_THE_AGENT_MUST_RUN_OR_EVIDENCE_IT_MUST_RETURN}}

## Write policy

{{READ_ONLY_OR_EXACT_DISJOINT_WRITE_SCOPE}}

If completing the objective requires leaving allowed scope, violating excluded scope, or changing plan authority, stop and return a blocker. Do not widen the assignment.

## Repository state

{{WORKTREE_BRANCH_BASE_REVISION_AND_CHANGES_TO_PRESERVE}}

## Side effects

{{DEPENDENCY_INSTALL_NETWORK_EXTERNAL_SYSTEM_DATABASE_COMMIT_PUSH_DEPLOY_AND_DESTRUCTIVE_ACTION_POLICY}}

Anything not explicitly permitted here is denied when it changes an external system or is destructive.

## Escalation

{{WHEN_TO_STOP_AND_RETURN_A_CONFLICT_OR_BLOCKER}}

## Expected return

Return changed files or findings, validation results, unresolved risks, and any assumption that needs main-agent review. Report only that the bounded assignment is ready for integration; do not claim the current user request or whole project is complete.
