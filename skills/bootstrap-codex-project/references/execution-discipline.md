# Execution discipline and delivery closure

Use this module when a project has long-running autonomous work, repeated
continuation prompts, bundled requirements, visible product work competing
with internal cleanup, repeated failed attempts, release artifacts, or
user-facing state that must reflect runtime truth.

This module refines execution inside existing authority. It never creates a
task, broadens scope, overrides safety or architecture, or authorizes an
external side effect.

## Contents

- [Ten promoted rules](#ten-promoted-rules)
- [Rule details](#rule-details)
- [Compatibility with existing rules](#compatibility-with-existing-rules)
- [Artifact mapping](#artifact-mapping)

## Ten promoted rules

| ID | Rule | Apply when |
| --- | --- | --- |
| `ED-01` | Validate, then advance | The user says only "continue", "next", or equivalent during an active plan |
| `ED-02` | Keep bundled work atomic | The user explicitly groups several required items or sets a finish-before-stop condition |
| `ED-03` | Preserve user-visible priority | Visible product outcomes compete with internal cleanup or audit work |
| `ED-04` | Canonicalize durable decisions | A user correction or decision should survive later turns or tasks |
| `ED-05` | Verify capabilities before declaring a blocker | A task appears to lack a tool, workspace, dependency, permission, or runtime capability |
| `ED-06` | Do not repeat an unchanged failed approach | An attempt has failed or produced no relevant progress |
| `ED-07` | Close the delivery contract | Work produces an artifact, release, publication, deployment, or source-control handoff |
| `ED-08` | Normalize consequential domain terms | A term's meaning changes architecture, configuration, data, safety, or acceptance |
| `ED-09` | Require user-visible effective-state evidence | Internal implementation or saved configuration is not enough for a user-facing feature |
| `ED-10` | Validate the change blast radius | A shared UI, configuration, schema, API, or platform change may affect sibling surfaces |

## Rule details

### ED-01: Validate, then advance

Resolve a bare continuation prompt against the active plan:

1. Read the current task and latest checkpoint.
2. Compare current evidence with every acceptance criterion for that task.
3. If anything is missing, finish the highest-value missing criterion.
4. If the task is complete, mark it complete and advance to the next authorized
   pending milestone.
5. If the plan is complete, follow its exact `on_complete` value.

Do not interpret "continue" as permission to repeat the last command, deepen
one subproblem indefinitely, select an unrelated roadmap item, or broaden
scope.

### ED-02: Keep bundled work atomic

When the user says that several items should be done together, or that work
must continue until a named boundary, make that set one completion unit.
Maintain an acceptance matrix or equivalent evidence list. A subset may be
reported as progress, but the unit is not complete until every required item
is verified, explicitly removed by the user, or recorded as a real blocker.

Do not force atomic treatment on independent suggestions that the user did not
bundle.

### ED-03: Preserve user-visible priority

Record why the current task is highest priority. Prefer the user's stated
outcome and visible failure over internally attractive cleanup. Internal
architecture, security, or reliability work may lead when repository evidence
shows it is a prerequisite or when a higher safety constraint requires it.
State that dependency instead of silently replacing the user's priority.

This rule changes sequencing, not product or architecture authority.

### ED-04: Canonicalize durable decisions

When a user correction or decision is consequential, repeated, or needed by a
future task, write it once to the correct durable owner:

- product behavior or non-goal -> product documentation or decision record
- architecture, data, compatibility, or safety boundary -> architecture or
  decision record
- current priority or temporary exclusion -> active plan
- current evidence and exact next action -> checkpoint

Later work may change it only through a new classified instruction. Do not
re-litigate an explicit decision merely because a generic practice suggests a
different default.

### ED-05: Verify capabilities before declaring a blocker

Before saying that work cannot continue because a tool, terminal, editor,
repository, dependency, permission, or runtime is unavailable:

1. Inspect the current workspace and callable tools.
2. Use safe discovery or a read-only probe.
3. Distinguish an unavailable capability from one failed invocation, stale
   conversation context, an approval boundary, or a missing dependency that
   can be installed within authority.
4. Record the concrete evidence and the smallest required user or external
   action.

Capability discovery does not grant permission to install, mutate external
systems, bypass approval, or perform destructive work.

### ED-06: Do not repeat an unchanged failed approach

For each material failed attempt, record:

- method or hypothesis
- observed outcome
- failure cause or remaining uncertainty
- what input, evidence, or strategy will change next

Do not repeat a method without new evidence or a changed condition. After an
unchanged failure, diagnose or switch strategy inside the same authorized
objective. Do not abandon the task for unrelated work merely because it is
difficult.

### ED-07: Close the delivery contract

When the objective includes an artifact, release, deployment, publication, or
source-control handoff, define the expected delivery evidence before claiming
completion. Include only relevant fields:

- version or revision
- artifact name and path or published location
- size, digest, signature, or other identity evidence
- validation results and known limits
- working-tree state
- commit, push, release, deployment, or synchronization state
- recovery or rollback information

Reporting an external state never authorizes changing it. Commit, push,
publish, deploy, and destructive actions still require the user's authority.

### ED-08: Normalize consequential domain terms

If a term can materially change the solution, derive its meaning from
authoritative project evidence or ask one plain-language question. Record the
accepted meaning in `docs/glossary.md` or the domain document that owns it.

Do not ask about harmless wording differences, and do not turn ordinary
language into a glossary ceremony.

### ED-09: Require user-visible effective-state evidence

For interactive product behavior, acceptance must cover what the user can
observe:

- effective state, not only saved intent
- pending and delayed states
- failure cause and impact
- next available action
- consistency after refresh, restart, rollback, or external change when
  relevant

Backend code, a successful command, or a persisted switch does not by itself
prove that the user-facing feature is complete.

### ED-10: Validate the change blast radius

Before editing a shared surface, identify its consumers and representative
boundaries. Validate the dimensions that match the change:

- sibling pages, callers, schemas, or platforms
- minimum and maximum supported size
- scaling, localization, overflow, scrolling, keyboard, loading, error, and
  stale states for UI work
- compatibility, migration, rollback, and partial failure for data or API work

Do not require a full-system test for an isolated change with no shared
consumer. Select the smallest representative matrix that can expose the real
blast radius.

## Compatibility with existing rules

These rules refine, rather than replace, existing Skill contracts:

- Authority still comes from the user's latest instruction and an active,
  exclusive `PLANS.md`; `ED-01` cannot select unauthorized roadmap work.
- `ED-02` does not prevent honest blocker reporting or user-approved deferral.
- `ED-03` never overrides security, safety, data, architecture, or explicit
  exclusions.
- `ED-04` uses existing canonical owners and requirement-change classes; it
  does not create another decision layer.
- `ED-05` verifies capability but does not broaden side-effect permission.
- `ED-06` changes method, not objective or scope.
- `ED-07` separates reporting from mutation; a delivery contract is not push,
  publish, deployment, or destructive authority.
- `ED-08` asks only when meaning changes the result.
- `ED-09` applies to user-facing behavior, not internal libraries with no user
  surface.
- `ED-10` uses a risk-proportional representative matrix, not mandatory
  exhaustive testing.

## Artifact mapping

Use the smallest durable owner:

| Need | Owner |
| --- | --- |
| Continuation, bundled completion, priority basis, delivery contract | `PLANS.md` |
| Decisions that must survive future work | product, architecture, glossary, or decision record |
| Attempts, blockers, changed strategy, artifact and Git state | `docs/work/current.md` |
| Durable agent behavior for the repository | `AGENTS.md` |
| Formal task target, verified capabilities, dirty state, and reporting owner | new-task handoff |
| Mechanically detectable planning or path conflicts | validation scripts and tests |

Do not add these artifacts to short projects that do not exhibit the matching
signals.
