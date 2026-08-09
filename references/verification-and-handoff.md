# Verification and Handoff

## Evidence Matrix

Match each claim to a fresh check:

| Claim | Minimum check |
|---|---|
| The intended file changed | Inspect diff and target path |
| The running version is the new version | Identify process, route, artifact, and health response |
| A bug is fixed | Re-run the original reproduction and a regression case |
| A UI is usable | Exercise the same touch, keyboard, orientation, and navigation path as the user |
| Data is synchronized | Compare the authoritative source and each client after cold start, refresh, and restart |
| History is efficient | Measure first load, incremental load, memory, cache hit, and reconnect behavior |
| A delete or migration is safe | Confirm exact target, backup/rollback, post-condition, and absence of unintended targets |

Tests are evidence, not the product definition. A passing test with a failed user path is a failed requirement.

Capture a baseline before a change whenever the task concerns behavior, UI, performance, synchronization, or deployment. The baseline should identify the running artifact/version and contain the smallest reproducible user path. Compare the same path after the change.

For this skill itself, run `scripts/verify-skill-release.ps1` before handoff. It combines regression, adversarial, artifact-continuity, parser, skill-structure, and experience-store checks. A status of `guard_ready_replay_pending` means the local guard implementation is validated but the matched real guarded user-path replay has not occurred; do not call that a completed effectiveness evaluation.

## Handoff Record

After interruption or context pressure, preserve one authoritative record containing:

```text
goal
plan_version
done
not_done
verified_facts
open_hypotheses
authorization
forbidden_actions
target_identity/version
risks_and_rollback
next_minimal_action
```

For multi-provider or multi-client work, `target_identity` must include provider, model, thread or task identity, client, permission mode, and route/port where applicable. A task cannot resume safely if those fields are unknown.

Do not create a parallel human conversation or map local folders into a conversation list to represent this record. Child-agent work remains an internal run unless the user explicitly asks to expose it.

## Stop Conditions

Stop and report instead of continuing when:

- authorization or identity is unclear;
- the target artifact/version cannot be identified;
- the source of truth conflicts with the displayed state;
- two causal attempts failed without new evidence;
- a third-party dependency would require unreviewed privileged behavior;
- the only available fix is destructive and no rollback exists.

## User-Facing Completion Format

Report:

1. Result: what changed or what remains unresolved.
2. Evidence: the fresh checks and their outcomes.
3. Impact: what the user can now do and what is unchanged.
4. Remaining risk: unknowns or untested paths.
5. Next action: one concrete, authorized step.
