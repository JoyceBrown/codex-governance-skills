# Fact-Forcing Pre-Action Gate

Self-evaluation is weak under time pressure. A deterministic gate should block the first risky action and require concrete facts before allowing a retry. The facts themselves create the context needed for better decisions.

Use [scripts/fact-gate.ps1](../scripts/fact-gate.ps1) or an equivalent host Hook. Do not gate every command; use the light routine gate once per session and the stronger gates at the first causal write or every destructive action.

## Gate contracts

| Action | Required facts |
|---|---|
| `routine` | Current user instruction, command purpose |
| `edit` | User instruction, target files, callers/consumers, public surface, source of truth, baseline |
| `write` | User instruction, target path, existing-capability search, callers/consumers, source of truth, baseline |
| `destructive` | User instruction, exact targets, authorization scope, rollback, source of truth, baseline |

After a gate passes, the same target may be retried without re-gating. A changed target, version, hypothesis, or destructive scope requires a new gate. The gate validates facts; it does not decide whether the proposed change is good.

## Evidence requirements

Facts should come from repository search, file inspection, logs, synthetic data, screenshots, real device checks, or a reproducible command. Never paste secrets or full production data. Quote the current user instruction rather than an old plan.

## Why this exists

The gate addresses the failure mode where an agent can recite a rule but still edits from an unverified assumption. It is a control surface for a future PreToolUse hook, not a claim that the current Codex host automatically intercepts every tool call.
