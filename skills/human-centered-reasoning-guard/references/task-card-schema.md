# Durable Task Card

The task card is the authoritative resumable state for a complex task. Keep it small and factual; do not store a transcript.

Required JSON fields:

```json
{
  "task_id": "stable task identity",
  "plan_version": "R1",
  "state": "planning|investigating|ready_to_write|executing|verifying|paused|blocked|complete",
  "state_reason": "why the task is in this state",
  "real_user_goal": "the outcome in the user's life",
  "visible_success": "what the user can observe and do",
  "authorization": ["allowed mutation scope"],
  "forbidden_actions": ["explicitly prohibited actions"],
  "verified_facts": ["evidence-backed facts"],
  "unknowns": ["unverified assumptions"],
  "target_identity": {"provider": "...", "model": "...", "thread": "...", "client": "..."},
  "target_version": "artifact, route, build, or process identity",
  "source_of_truth": ["authoritative source or endpoint"],
  "baseline": ["pre-change screenshot, metric, or reproduction"],
  "attempts": 0,
  "attempt_id": null,
  "hypothesis_id": null,
  "last_result": null,
  "last_verified_at": null,
  "rollback_ref": null,
  "next_action": "one smallest safe next action",
  "updated_at": "ISO-8601"
}
```

Before a high-risk write, the card must identify the target identity, current version, source of truth, baseline, authorization, and rollback. State transitions are restricted to the documented order; use [scripts/transition-task-state.ps1](../scripts/transition-task-state.ps1) instead of editing `state` by hand. Each `executing` transition creates an `attempt_id` and increments `attempts`. The reset tier starts when the same causal attempt fails twice; use a new hypothesis and preserve the previous evidence.

Use [scripts/write-task-card.ps1](../scripts/write-task-card.ps1) to write atomically, [scripts/validate-task-card.ps1](../scripts/validate-task-card.ps1) before resuming, and [scripts/preflight-task.ps1](../scripts/preflight-task.ps1) before a high-risk tool call. The card is task state, not a conversation list and not a second source of truth for product data.

`plan_version` identifies the active planning hypothesis, not a promise that it remains correct. When facts or user goals change, reconcile the plan with [scripts/reconcile-plan.ps1](../scripts/reconcile-plan.ps1) and record the decision before changing `next_action`. Use [scripts/drift-report.ps1](../scripts/drift-report.ps1) to compare intended state with the artifact, runtime, authoritative source, and user observation; do not mark `complete` while drift remains at level 2 or 3.

Before moving from `verifying` to `complete`, validate a redacted [completion receipt](completion-receipt.md) with [scripts/validate-completion-receipt.ps1](../scripts/validate-completion-receipt.ps1). Record its receipt ID and concise evidence references in `last_result`; do not use the task card itself as proof that a user path passed.
