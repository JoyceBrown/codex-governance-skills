# Change-aware project context review

Use this module only when a context audit needs a stable comparison boundary or supports a consequential project judgment. It strengthens review evidence without turning project bootstrap into a multi-role deliberation workflow.

## Activation

Enable the module when at least one signal exists:

- an audit or refresh compares a named baseline with the current repository;
- prior findings, decisions, or verification results must be rechecked;
- the live tree may change during a multi-step or cross-session review;
- a reuse-versus-build, architecture, release, or continue/pivot/stop judgment depends on material uncertain evidence.

Do not enable it for a greenfield project, a routine short documentation refresh with no comparison boundary, or an ordinary implementation task. This module never invokes `deliberate-project` or its three-role baseline.

## Declare the case boundary

Keep two axes independent:

```text
continuity_mode: Initial | Re-review
comparison_mode: Current-state | Delta
```

Use `Re-review` only when a prior project-specific record governs the comparison. Use `Delta` only when both a named baseline and current state are available. Without a real baseline, remain in `Current-state` and disclose the missing comparison boundary.

## Bind observations to a snapshot

Prefer a commit, content-addressed frozen copy, or exported immutable revision. Otherwise create one case-level `Manifest-bound` identity from the relevant paths and hashes; never call a live tree immutable.

Attach item-level fingerprints only to live, high-drift, or consequential evidence. Before writing artifacts or reporting the review:

1. check the relevant snapshot or manifest for drift;
2. mark affected observations `Snapshot-stale` when material files changed;
3. rerun only dependent inspection and judgment work against a new identity;
4. never merge observations from two snapshots as one project state.

## Keep claim kind and project state separate

Use a lightweight `claim_kind` only when a reader could confuse direct evidence with interpretation:

- `observation`: directly inspected or reproduced project state;
- `judgment`: an interpretation derived from observations;
- `preference`: an explicitly authorized priority or value choice;
- `proposal`: a recommendation that has not been adopted.

Continue to use `Verified`, `Decided`, `Planned`, `Assumed`, and `Open` as the project's evidence or authority state. The axes are orthogonal: a preference may be `Decided`, an observation may be `Verified`, and a proposal may remain `Open`. Do not import a second full finding or judgment ontology.

## Scale evidence checks by claim type

- Verify present repository facts by direct inspection or a reproducible command.
- For consequential causal, predictive, comparative, or recommendation judgments, record one concrete counterargument or boundary condition.
- Trace materially corroborating external evidence to its upstream lineage. Several summaries derived from one source count as one lineage.
- Seek an independent source, instrument, or reproduction path only when it could change the judgment. Do not demand multiple sources for a directly observed local fact.

Stop another review pass when the declared questions are answered, remaining gaps are explicit, and more work has low expected decision value. Information-gain stopping governs review depth only; it never ends authorized implementation before acceptance criteria or a delivery contract are satisfied.

## Report review coverage without claiming project completion

Use a namespaced field:

```text
review_completion: Complete | Partial | Blocked
```

- `Complete`: the declared review boundary was responsibly examined and another bounded pass has low expected information value.
- `Partial`: useful review work is complete, but a material area, comparison, or verification remains; name it and its consequence.
- `Blocked`: no responsible conclusion can be produced within the declared boundary because required evidence or a safe inspection path is unavailable.

`review_completion` never sets or implies task, active-plan, release, user-request, or project completion. A partial review does not automatically block unrelated artifact work, and a complete review does not authorize implementation or external side effects.
