---
name: human-centered-reasoning-guard
description: Use when a task involves software changes, debugging, UI/UX, performance, caching, synchronization, networking, permissions, deployment, deletion, migration, multiple agents or providers, repeated failure, user reports that a fix did not change the result, or work resumed after interruption. Reframe the work around the user's real-world outcome, verify root causes and boundaries, protect authorization, and capture only validated reusable lessons.
---

# Human-Centered Reasoning Guard

## Purpose

Treat the user's lived outcome as the primary requirement. Before changing a system, distinguish the symptom from the real goal, separate facts from assumptions, and choose the smallest reversible action that increases certainty. After acting, verify the path a non-technical user actually follows. Do not claim completion without fresh evidence.

This is a guard layer, not a replacement for domain skills, tests, security controls, or product decisions.

## Activation Tiers

Use the light tier for routine changes: state the real goal, the visible success condition, authorization, and one verification step.

Use the full tier when any trigger in the description matches, or when the work crosses a system boundary (client/server, source/cache, provider/thread, process/network, project/production).

Use the reset tier immediately when the same symptom survives two attempts, the user says the result is unchanged, tests pass but the user fails, evidence conflicts, or the plan has drifted after a handoff/compaction. Stop the current patch path and reframe the problem from first principles.

Do not run the full tier for a simple explanation, a single read-only command, or a user request explicitly limited to analysis.

For a deterministic recommendation, run [scripts/classify-task-tier.ps1](scripts/classify-task-tier.ps1) with the bounded facts in [references/task-tiering.md](references/task-tiering.md). Treat `reset` as a direction change, not a reason to stop the workbench.

At the start of a non-trivial turn, use [scripts/invoke-guard-workflow.ps1](scripts/invoke-guard-workflow.ps1) to route the tier, task-card preflight, target identity, drift state, and next bounded action. It is a decision layer: `mutation_allowed` is false until the required evidence is present, and reset/drift blocks redirect to investigation rather than killing the workbench.

## Preflight Contract

Create an internal task card before a write or risky action:

```text
Real user goal:
Visible success state:
Current observed behavior:
Constraints and non-goals:
Authorized actions:
Forbidden actions:
Verified facts:
Unknowns and assumptions:
System boundaries and facts sources:
Target identity (provider, model, thread, client, permission mode):
Target version/route/artifact:
Baseline (screenshot, metric, reproduction, or response):
At least two competing root-cause hypotheses:
Reversible options and trade-offs:
Risk, rollback, and resource budget:
User-verifiable acceptance checks:
Smallest next action:
```

Resolve language precisely:

- "analysis-only/answer-only/no-action" means read-only; do not mutate files, accounts, network, production, or task state.
- "continue" means resume the last safe, unfinished step; never repeat a failed action without new evidence.
- "authorize" authorizes only the named scope and target.
- "publish/replace production" requires an explicit target, artifact identity, health check, and rollback path.
- Silence is not approval. A user correction is evidence, not an invitation to make unrelated changes.

## Fact Gate

Before the first causal edit or write, run [scripts/fact-gate.ps1](scripts/fact-gate.ps1) with a small redacted JSON object. Use `routine` once for a low-risk session, `edit` for an existing-file change, `write` for a new or generated artifact, and `destructive` for deletion, migration, replacement, restart, or account/network changes. The gate must contain the current instruction, target, consumers, source of truth, and baseline required by [references/fact-gate.md](references/fact-gate.md). Do not gate every harmless read or repeat a gate for the same target/version/hypothesis. This script is a callable guard for a future host Hook; it does not currently intercept every Codex tool call automatically.

## Goal Integrity

After the fact gate and before the causal action, run [scripts/goal-integrity-gate.ps1](scripts/goal-integrity-gate.ps1). State how the proposed action changes the user's visible success state, what observation would disprove that claim, and what is explicitly out of scope; use `mutate` for writes and `complete` only after a fresh user-path pass. A failed goal gate blocks that action and redirects to evidence collection or a new hypothesis. It does not terminate the workbench or authorize a different action.

## Reframe Before Fixing

Ask internally, in this order:

1. What does the user need to accomplish in real life?
2. What should they see, feel, and be able to do when it works?
3. What cost is the current behavior imposing (waiting, refreshes, restarts, confusion, data loss, technical investigation)?
4. Which layer owns the behavior: source data, execution state, transport, cache, presentation model, UI interaction, permissions, or environment?
5. What would a from-scratch design do differently?

List a minimum of two competing explanations. For each, state a prediction and the cheapest observation that could disprove it. Do not convert a guess into a fix.

## Execution Guardrails

- Prefer existing, maintained libraries and local patterns, but reject reuse that preserves the wrong architecture.
- Make one causal change at a time when diagnosing; partition broad requests into independently verifiable slices.
- Keep internal execution logs, derived files, and user-facing results separate.
- Keep human-visible task identity separate from internal run IDs, child agents, caches, and local project folders unless the user explicitly requests a mapping.
- Treat the active plan as a versioned hypothesis. When a new request, blocker, or verified observation appears, reconcile it before changing the plan; do not preserve plan wording at the expense of the user's current goal.
- Do not create parallel human sessions, providers, task databases, or sources of truth to hide a continuity problem.
- Preserve a rollback point before deletion, migration, restart, provider change, or production replacement.
- Set a time, token, memory, network, and interaction budget. If the process cost exceeds the expected benefit, downgrade or stop.
- Count attempts against the same hypothesis, target version, and user-visible symptom. After two failed attempts, use reset tier. After three failures or evidence of shared coupling, question the architecture instead of making another patch.

## Task State

For multi-step work, keep the durable card valid and move it with [scripts/transition-task-state.ps1](scripts/transition-task-state.ps1), never by hand-editing `state`. The normal path is `planning -> investigating -> ready_to_write -> executing -> verifying -> complete`; `paused` and `blocked` are explicit recovery states. Every `executing` transition requires a hypothesis and records a new attempt ID. `complete` requires a fresh verification timestamp. A failed attempt returns to `investigating` or `executing` only with new evidence or a new hypothesis.

## Plan Reconciliation and Drift

Use [scripts/reconcile-plan.ps1](scripts/reconcile-plan.ps1) when a new user request, blocker, or discovery conflicts with the active plan. Classify it as `integrate`, `defer`, `supersede`, or `clarify` using [references/plan-reconciliation.md](references/plan-reconciliation.md); `clarify` blocks mutation when goal, authorization, identity, or source of truth conflicts. Use [scripts/drift-report.ps1](scripts/drift-report.ps1) before resuming a long task, after an unchanged result, or before completion. Compare intended goal, plan version, artifact, runtime, authoritative source, authorization, and user observation. A drift level of 2 or 3 stops the current patch path; it does not terminate the workbench.

For multi-provider or multi-client tasks, explicitly verify provider, model, thread, client, and route identity before treating artifact or runtime state as aligned.

Use [scripts/validate-target-identity.ps1](scripts/validate-target-identity.ps1) whenever a task crosses provider, model, thread, client, route, or permission boundaries. An observed identity without an expected identity is `observed_only`, never a match.

## Verification and Communication

Use evidence appropriate to the claim:

| Claim | Required evidence |
|---|---|
| Code changed | Diff or file inspection |
| Build succeeds | Fresh full build output with exit status |
| Bug fixed | Original reproduction now passes |
| User requirement met | Requirement-by-requirement check on the real user path |
| Multi-client consistency | Same identity/source observed from each client after refresh/restart |
| Performance improved | Before/after measurement under the relevant cold/warm and failure conditions |

Report only a concise decision summary, evidence, impact, and next action. Do not expose private chain-of-thought or bury the verdict in execution narration. If verification is incomplete, say exactly what remains unknown.

For a substantial skill revision or repeated failure pattern, compare matched anonymized cases with [scripts/score-evaluation.ps1](scripts/score-evaluation.ps1) using [references/evaluation.md](references/evaluation.md). Report reliability changes separately from duration and tool-call cost; do not treat a passing unit test or a subjective impression as proof of user benefit.

Run [scripts/run-regression-tests.ps1](scripts/run-regression-tests.ps1) after changing any bundled guard script. This verifies only guard behavior with synthetic redacted cases; it does not replace matched real-task evaluation.

Before declaring a multi-step task complete, run [scripts/validate-completion-receipt.ps1](scripts/validate-completion-receipt.ps1) using [references/completion-receipt.md](references/completion-receipt.md), then [scripts/review-completion-counterfactual.ps1](scripts/review-completion-counterfactual.ps1) using [references/counterfactual-review.md](references/counterfactual-review.md). The receipt requires verified identity, authoritative source, artifact, runtime, a passing user path, and drift level 0; the counterfactual review attempts to disprove success through wrong-target, stale-runtime, source-divergence, refresh, and rejected-path checks. On failure, return to verification or investigation; do not rewrite the goal or silently lower acceptance.

Before handing off a substantial revision of this skill, run [scripts/verify-skill-release.ps1](scripts/verify-skill-release.ps1). A replay-pending status proves only local guard readiness, never a real user-path improvement.

After verified plan, drift, or completion records exist, use [scripts/sync-durable-ledger.ps1](scripts/sync-durable-ledger.ps1) under [references/ledger-bridge.md](references/ledger-bridge.md) to checkpoint their redacted status into the existing durable ledger. Do not create a second task database or hand-edit the durable ledger.

## Failure and Recovery Protocol

When a result is unchanged:

1. Record the exact user-visible symptom and reproduction path.
2. Compare the delivered artifact, running version, route, identity, and cache against the intended target.
3. Check whether the observation came from the correct source of truth.
4. Reopen the root-cause hypotheses; include an architectural and an environment explanation.
5. Run one discriminating observation before another fix.
6. Update the task card and stop if authorization or state ownership is unclear.

After interruption, compaction, or handoff, restore from the durable task card described in [references/task-card-schema.md](references/task-card-schema.md). Validate the card before resuming. Do not trust a stale summary, an old plan, a process that merely remains running, or another agent's success report without independent verification.

## Experience Learning

Record only an abstract, redacted event when a task produces a non-obvious, verified lesson. Store observations separately from reusable rules. Use the lifecycle and conflict rules in [references/memory-policy.md](references/memory-policy.md).

Use [scripts/record-experience.ps1](scripts/record-experience.ps1) only with a short JSON object containing already-redacted fields. It appends a project-isolated candidate and does not infer, upload, promote, or modify this skill. Use [scripts/retrieve-experience.ps1](scripts/retrieve-experience.ps1) to retrieve a small relevant set, and [scripts/review-experience.ps1](scripts/review-experience.ps1) for an explicit, append-only state transition. The retrieval wrapper uses the bundled Python standard-library parser when available for the measured large-store budget and retains a validated PowerShell fallback; both read the same store and return at most 20 records. Validate the store before use.

Before automatic retrieval in a long-running task, run [scripts/audit-experience-store.ps1](scripts/audit-experience-store.ps1). It is read-only and reports expired or conflicting records; resolve them explicitly before promotion or reuse. Never let the audit silently rewrite memory.

For real-task evaluation, use [scripts/collect-evaluation-candidates.ps1](scripts/collect-evaluation-candidates.ps1) under [references/evaluation-collection.md](references/evaluation-collection.md). It may read local conversation sources but must retain only redacted, review-only candidates. Then use [scripts/build-evaluation-cases.ps1](scripts/build-evaluation-cases.ps1) to group candidates and create a paired baseline/guarded review template, followed by [scripts/adjudicate-evaluation-cases.ps1](scripts/adjudicate-evaluation-cases.ps1) to confirm or reject historical evidence from ordered role signals. Do not treat a keyword match as a fact, a memory rule, or a user-visible conversation; do not score the template until an authorized replay or human review verifies each outcome, especially the guarded side.

Build the replay queue with [scripts/build-replay-manifest.ps1](scripts/build-replay-manifest.ps1). A historical failure may prioritize a replay, but it does not authorize a live mutation or prove the guard's user-path result.

Run [scripts/validate-evaluation-artifacts.ps1](scripts/validate-evaluation-artifacts.ps1) before treating a local evaluation corpus as usable. It verifies source-to-replay case continuity and redaction, not the real guarded outcome.

Use [scripts/evaluate-guard-coverage.ps1](scripts/evaluate-guard-coverage.ps1) to test whether confirmed historical risk features would reach the correct guard. Treat its result as policy coverage only, never as a real guarded replay or user-path pass.

After an authorized replay, record results with [scripts/record-evaluation-outcome.ps1](scripts/record-evaluation-outcome.ps1), then pair and score them with [scripts/compile-scored-evaluation.ps1](scripts/compile-scored-evaluation.ps1). Both are evidence recorders, not replay executors.

## Reference Navigation

- Root-cause, user-cost, and architecture checks: [references/reframe-and-failure-patterns.md](references/reframe-and-failure-patterns.md)
- Plan changes and long-task drift: [references/plan-reconciliation.md](references/plan-reconciliation.md)
- Host Hook coordination: [references/hook-integration.md](references/hook-integration.md)
- Completion evidence and false-completion prevention: [references/completion-receipt.md](references/completion-receipt.md)
- Adaptive light/full/reset selection: [references/task-tiering.md](references/task-tiering.md)
- Redacted local evaluation collection: [references/evaluation-collection.md](references/evaluation-collection.md)
- Single-ledger checkpoint bridge: [references/ledger-bridge.md](references/ledger-bridge.md)
- Completion disproof review: [references/counterfactual-review.md](references/counterfactual-review.md)
- Memory scope, confidence, privacy, forgetting, and conflicts: [references/memory-policy.md](references/memory-policy.md)
- Performance and bounded processing: [references/performance-budget.md](references/performance-budget.md)
- Handoff, acceptance, and realistic verification: [references/verification-and-handoff.md](references/verification-and-handoff.md)
- Durable task-card fields and resume rules: [references/task-card-schema.md](references/task-card-schema.md)
- Third-party skill review and supply-chain boundaries: [references/supply-chain.md](references/supply-chain.md)

## Non-Goals

Do not use this skill to replace domain-specific debugging, security review, accessibility review, product strategy, tests, or human authorization. Do not let it become a second task system, a complete conversation archive, an automatic self-modifying prompt, or a reason to over-process simple requests.
