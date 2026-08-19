# Plan Reconciliation and Drift

Treat a plan as a versioned hypothesis, not as a source of truth. When a new user request, blocker, or verified observation appears, compare it with the active goal and classify the change before editing the plan:

| Decision | Use when | Required consequence |
|---|---|---|
| `integrate` | The goal is unchanged or more precise | Keep the goal, add acceptance or sequencing detail |
| `defer` | The request is valid but outside the current milestone | Preserve it as a later item without changing the active goal |
| `supersede` | Verified evidence or an explicit goal change invalidates the plan | Create a new plan version and name the superseded version |
| `clarify` | Goals, authorization, identity, or source of truth conflict | Do not mutate; record the smallest open question |

Use `scripts/reconcile-plan.ps1` to validate this decision. It records the reasoning but does not silently rewrite a plan document.

Use `scripts/drift-report.ps1` before resuming a long task or after an unchanged result. Compare the goal, plan, intended artifact, running version, provider/thread/client identity, authoritative source, authorization, and user-visible observation. Drift levels are:

- `0`: aligned and safe to continue;
- `1`: stale or unknown evidence; rebaseline before writing;
- `2`: artifact/runtime/user mismatch; investigate the owning boundary;
- `3`: goal, authorization, identity, or source conflict; block mutation and clarify.

Never mark a task complete from plan status alone. Completion requires a fresh authoritative check and a passing user path.
