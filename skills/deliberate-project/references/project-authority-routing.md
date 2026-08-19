# Project boundary, authority, and conclusion routing

Use the snapshot section whenever current-state or delta evidence must be bound to the project the user actually named. Use the remaining sections when an inquiry must explain where a conclusion belongs or whether anyone has authority to decide or act on it. The module adds boundary and governance controls to the read-only inquiry; it does not install bootstrap conventions or modify project artifacts.

## Snapshot equivalence

A stable snapshot is useful only when it represents the requested state. Record the target as `Commit`, `Live-worktree`, `Frozen-copy`, `Export`, `Deployed-state`, or `Manifest-bound`, then establish `snapshot_equivalence=Verified | Qualified | Unverified | Not-applicable` before treating it as current evidence.

For a current-state or delta boundary, inspect the applicable sources of divergence rather than assuming a clean commit is the whole project:

- tracked modifications and staged changes;
- relevant untracked and ignored overrides without exposing secrets or indiscriminately opening every ignored file;
- submodule revisions, LFS placeholders, symlink targets, generated artifacts, vendored material, and build outputs when they can change behavior;
- deployment manifests, environment-specific configuration, feature flags, migrations, external state, and runtime version/configuration when the user asks about deployed or operational behavior.

Keep a compact snapshot-equivalence record:

```text
requested_state
selected_snapshot
included_state_classes
excluded_state_classes
divergence_checks
material_divergences
snapshot_equivalence
residual_gap
```

Use `Verified` only when material divergence paths were checked and the selected snapshot represents the requested state. Use `Qualified` when known exclusions are bounded and do not affect the claim. Use `Unverified` when a plausible material divergence path remains unresolved. A current-state priority area with `snapshot_equivalence=Unverified` is not responsibly examined and requires `Partial`; do not bind all roles to a stable but potentially wrong commit and call their agreement corroboration.

## Authority activation

Read this module when at least one signal exists:

- several roadmap, plan, todo, status, checkpoint, or handoff artifacts could appear actionable;
- a requirement change may alter durable product, architecture, safety, compatibility, data, or support boundaries;
- the user asks how findings should enter durable project records;
- a recommendation depends on unclear decision rights, execution authority, or residual-risk acceptance.

Do not load a full project-planning model for an ordinary technical review. Do not require `PLANS.md`, `docs/roadmap.md`, `docs/work/current.md`, or any other bootstrap filename unless the inspected project already adopts that convention.

## Separate owner and authority dimensions

Map only dimensions supported by project evidence:

- `source_authority`: the source qualified to establish a fact or governing requirement;
- `durable_owner`: the existing artifact or system that canonically stores the conclusion;
- `decision_owner`: the person or body authorized to choose objectives, tradeoffs, waivers, or residual risk;
- `execution_authority`: the instruction, plan, or approval that authorizes work or side effects;
- `verification_owner`: the evidence source or responsible party that can establish acceptance.

These dimensions may point to different owners. Do not infer one from another. The primary agent remains synthesis owner for the inquiry, but that role grants no project decision or execution authority.

When evidence does not establish an owner, report `authority_gap` or `User-dependent`; do not appoint one. A proposed `recommended_canonical_owner` is a judgment for an authorized project owner to accept, not a discovered fact or a write instruction.

## Inspect project planning semantics without imposing filenames

When applicable, determine which existing artifacts express:

```text
long_term_direction: desired future outcomes without automatic execution authority
active_execution_authority: currently authorized work and its limits
progress_record: completed work, failures, evidence, and handoff state without creating work
```

Treat these as semantic roles, not mandatory files. Report competing or ambiguous authority as a finding. Never convert a roadmap, backlog, checkpoint, issue list, or recommendation into execution authority unless the project's governing evidence explicitly does so.

## Keep requirement impact and observed change orthogonal

When the project already uses the bootstrap context model, or the inquiry needs an equivalent impact analysis, record a separate `requirement_change_class`:

- `task_adjustment`: changes the current task method or acceptance detail without altering durable boundaries;
- `priority_branch`: temporarily changes execution priority without changing the long-term destination;
- `roadmap_change`: changes durable product, architecture, safety, compatibility, data, platform, or support boundaries.

Do not derive this field from `continuity_mode`, `comparison_mode`, `technical_change_state`, or `stakeholder_response_state`. A `Delta` is not automatically a roadmap change, and a resolved technical finding does not prove that an authorized owner accepted a requirement change. When the project's own terminology differs, preserve it and state any conditional mapping rather than rewriting its authority model.

## Route conclusions and acceptance evidence

For a material conclusion that may need durable follow-through, report only the applicable fields:

```text
observed_owner
recommended_canonical_owner
decision_owner
execution_authority
authority_gap
acceptance_evidence_target
```

Match acceptance evidence to the claim:

- present project behavior: direct inspection or reproducible observation;
- implementation or configuration: a representative test, build, probe, or rendered behavior;
- normative requirement: current applicable primary authority plus project mapping;
- preference or governance: explicit decision-right evidence;
- causal or predictive judgment: mechanism, material alternative explanation, indicators, and uncertainty.

Prefer a reproducible, side-effect-free check when it fits the claim. Mechanical checks cannot establish stakeholder preference, legal applicability, causal explanation, or decision authority by themselves.

## Preserve the inquiry boundary

This routing is advisory and read-only. It does not create or update a document, reclassify a project requirement as an adopted decision, change plan authority, authorize implementation, or accept residual risk. If the same user request separately authorizes implementation, hand the accepted conclusion to the governing implementation workflow after the inquiry report is stable.
