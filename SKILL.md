---
name: bootstrap-codex-project
description: Turn a software idea or existing repository into a minimal, accurate, maintainable Codex context system. Use when bootstrapping or auditing a project; creating or repairing README.md, AGENTS.md, or project documentation; defining an evidence-based MVP or first vertical slice; comparing reuse with custom implementation; assessing solo-software stage or release readiness; deciding whether to continue, simplify, pivot, or stop; separating active plans from roadmaps; classifying mid-project requirement changes; handing work to a new task or subagent; learning from validated project friction; deciding whether nested AGENTS.md files are needed; or auditing stale and duplicated AI instructions. Adapt output to user experience and repository evidence. Add advanced Codex configuration, skills, planning controls, rules, hooks, MCP guidance, or custom agents only for a demonstrated need.
---

# Bootstrap Codex Project

Build the smallest context system that lets a human understand the project and lets Codex work correctly. Ground every artifact in the user's brief or repository facts. Prefer a few accurate files over a complete-looking framework.

Treat the Skill as a translator between natural-language intent and professional project structure. Keep the user entry simple, make the internal diagnosis broad, and keep generated output proportional to demonstrated need. Do not require users to know Codex surfaces or planning terminology before the Skill can help them.

## Core model

Keep three semantic layers separate:

1. **Project facts**: `README.md`, `docs/`, code, tests, and decision records explain what the project is and how it works.
2. **Codex guidance**: `AGENTS.md` explains how Codex should work in this repository.
3. **Optional capabilities**: `.codex/`, `.agents/skills/`, MCP, rules, hooks, custom agents, and scheduled tasks exist only for demonstrated needs.

When long-running work needs plans, keep direction, execution authority, and progress separate. A roadmap describes future direction; an active plan authorizes current work; a checkpoint records progress. Do not create this planning layer for an ordinary short task.

Assign every fact one canonical owner. Link to that owner instead of copying the same explanation into several files.

Use an explicit evidence state whenever a reader could confuse intent with reality:

- **Verified**: observed in repository evidence or a successfully run command.
- **Decided**: supplied by the user or an authoritative project decision.
- **Planned**: accepted direction that is not implemented yet.
- **Assumed**: reversible working assumption that still needs confirmation.
- **Open**: unresolved question or conflicting evidence.

Do not turn filenames, package names, dependencies, or model output into stronger claims than their evidence supports.

## Select the mode

Infer the mode without asking when the situation is clear:

- **Greenfield**: The user provides an idea and the target is empty or not yet created.
- **Existing repository**: Code or project configuration already exists.
- **Audit or refresh**: The user asks to review, simplify, repair, or update existing context files.

For an existing repository, resolve `<skill-dir>` to the directory containing this `SKILL.md`, then run `python "<skill-dir>/scripts/inspect_project.py" <project-root>` before proposing files. Treat its output as evidence, then read only the relevant files it identifies. If `scan.complete` is false, rerun with a higher limit or perform targeted reads before inferring that something is absent. Do not infer commands, frameworks, paths, or architecture from naming alone.

Do not load experience learning merely because a private registry exists. After identifying the project type and concrete risk signals, make one bounded `relevant` query; read `references/experience-learning.md` only when that query returns a matching Shadow or Active pattern, the user asks the Skill to remember or improve, or the current run produces capture-eligible friction. Treat Shadow as verification-only and Active as advisory until repository evidence confirms it. Finalize only runs that actually loaded or changed this module.

## Run the workflow

### 1. Establish the project definition

Normalize the available information into:

- purpose and target users
- observed problem evidence and the current alternative when product value is in scope
- concrete user outcome
- primary workflow
- first-release value loop, success signals, and stop or reassessment conditions when relevant
- scope and explicit non-goals
- solo delivery constraints such as available time, budget, operating cost, and maintenance capacity when they affect the result
- technology and deployment facts
- repository map and verified commands
- evidence state for material claims
- quality, safety, and completion requirements
- current focus and any explicitly deferred work
- priority basis, bundled completion boundary, and exact continuation behavior
- user-visible acceptance and delivery evidence when the project has those surfaces
- consequential domain terms, repeated failed attempts, and verified capability blockers
- whether a roadmap, active plan, or cross-session checkpoint already exists
- unresolved decisions

Read `references/interview-and-profiles.md` when important information is missing or when choosing an output profile. Ask no more than three questions at a time, use plain language, and ask only questions whose answers change the architecture, generated artifacts, plan authority, or safety posture. When a reversible assumption is sufficient, state it and continue.

### 2. Inspect before writing

For non-empty targets:

1. Read the existing `README.md`, applicable `AGENTS.md`, package manifests, documentation index, test configuration, and CI entry points.
2. Distinguish repository facts from human policy. Derive facts from files; obtain policy from the user or existing authoritative instructions.
3. Preserve accurate human-authored content.
4. Identify contradictions, stale paths, duplicated explanations, and guessed commands.
5. Identify roadmap, plan, todo, and current-work files that could all appear executable.
6. Never overwrite an existing file merely to match a template.

For a cold-start continuation, compare the current repository revision, active plan, requirements revision/hash, and generated handoff before using old notes. A missing historical item is an explicit unknown; do not manufacture a prior consensus or repeat a completed research question when a verified receipt exists.

### 3. Choose the smallest output profile

Use one of the profiles defined in `references/interview-and-profiles.md`:

- **Minimal** for small or early projects.
- **Standard** for active multi-module software.
- **Advanced** only for demonstrated tool, safety, automation, or delegation requirements.

Do not equate project size with configuration count. A large project may need only precise documentation and layered `AGENTS.md` files. A small high-risk project may need rules or hooks.

### 4. Select optional modules

Select optional modules independently from the output profile. A Standard project does not automatically need planning controls, and a Minimal project may need one when it has a concrete recurring failure.

Enable the solo-software delivery module when the user is shaping a first release, asks whether a product or milestone is ready to advance, needs an evidence-based reuse-versus-build decision, is preparing a release, or must decide whether to continue, simplify, pivot, or stop. Read `references/solo-software-delivery.md` completely before proposing lifecycle gates or delivery artifacts. Do not enable it for an ordinary isolated bug fix, explanation, or implementation request merely because the repository is software.

Enable the change-review module only when an audit has a real baseline or prior review record, the inspected tree may drift during a consequential review, or a material architecture, reuse, release, or direction judgment needs stronger evidence handling. Read `references/change-review.md` completely before declaring comparison or review completion. Do not enable it for greenfield work, a routine short documentation refresh, or ordinary implementation. It governs review coverage only; it never invokes a multi-role deliberation workflow or changes task, plan, release, or project completion.

Enable the planning-authority module only when at least one signal exists:

- work must survive context resets or multiple sessions
- the repository contains both a long-term roadmap and a current plan
- the user temporarily reprioritizes work without abandoning long-term goals
- Codex has selected tasks from the wrong plan
- several plan, todo, or status files can appear simultaneously actionable
- the user explicitly requests autonomous continuation with controlled stopping conditions

When enabled, read `references/planning-authority.md` completely before proposing artifacts. Use its plain-language questions and migrate existing content conservatively. Do not make users design plan IDs, authority markers, or file routing themselves.

When cross-session recovery, old-project takeover, or competing context files are part of the task, also read `references/context-ownership-and-migration.md`. Use its ownership matrix and `KEEP`/`UPDATE`/`ARCHIVE`/`SUPERSEDE`/`CONFLICT`/`UNKNOWN` classification before moving facts. Keep the active plan and current requirements as the only execution authority; carry IDs and hashes instead of copying whole explanations.

Read `references/plan-navigation.md` only when an approved multi-stage route has demonstrated structural drift across context resets, or a temporary priority branch needs an explicit continuity parent and return target. Treat route coordinates as optional annotations of the active plan; never create another Skill, task list, current-task field, or completion mechanism for them.

When the user adds or changes a requirement during ongoing work, or when work must continue in a new task, fork, or subagent, read `references/change-intake-and-agent-handoff.md` completely. Classify the change by its real effect, not by casual wording. Ask one plain-language question only when the answer changes durable project boundaries, what work should be restored later, or who has authority to alter the plan.

When long-running software work shows bare continuation prompts, bundled
finish-before-stop requirements, repeated failed attempts, user-visible work
competing with internal cleanup, release artifacts, consequential terminology,
or effective-state and blast-radius risk, read
`references/execution-discipline.md` completely. Apply only the rules whose
observable signals match; they refine execution inside existing authority and
never broaden scope or side-effect permission.

Enable experience learning independently from the output profile:

- `off`: do not capture or suggest experience candidates.
- `ask`: point out a reusable lesson after real friction and require current confirmation before saving it.
- `auto_sanitized`: use this default; save structured, sanitized candidates after real failures or user corrections, then automatically audit their private lifecycle.

The default mode does not scan or finalize the registry on an ordinary clean run with no matching signal and no reusable friction.

The registry tool enforces these modes: `off` rejects writes and `ask` requires a current confirmation flag. Sanitization is defense in depth, not proof that arbitrary text is safe; summarize structurally and inspect uncertain content before capture. The private lifecycle automatically moves evidence through Candidate, Shadow, Active, conflict quarantine, and rollback. It never resolves semantic ambiguity by recency alone, never locally overrides a promoted Skill rule, and never edits or publishes the formal Skill. Do not create project documentation merely to support the private registry. Project rules still belong in project-authoritative files.

### 5. Present the artifact plan

Before broad edits, show a compact plan with four groups:

- create
- update
- keep unchanged
- intentionally skip

Give one reason for each non-obvious file. If the user explicitly requested generation, proceed after the plan unless an existing file would be replaced, a security-sensitive setting would change, or a consequential command would run. Confirm those cases before acting.

### 6. Generate semantic artifacts

Use the matching files under `assets/templates/` as structural starting points. Adapt them to the project; do not leave unused sections or template placeholders.

Apply these ownership rules:

- Put the short project introduction, setup, and navigation in `README.md`.
- Put product behavior and boundaries in `docs/product.md`.
- When the solo-software delivery module is active, put problem evidence, the current alternative, the core value loop, first-release boundaries, success signals, and reassessment conditions in `docs/product.md`; do not create a parallel product brief or MVP file unless an existing project already owns those names.
- Put module boundaries and data flow in `docs/architecture.md`.
- Put durable reuse-versus-build conclusions in the applicable architecture or decision owner. Create a separate research document only when the comparison is substantial and must be revisited independently.
- Put entity meaning and invariants in `docs/data-model.md` when the domain is non-trivial.
- Put ambiguous domain terms in `docs/glossary.md`.
- Put durable decisions and tradeoffs in `docs/decisions/`.
- Put release checks in `docs/testing.md` and operational release, rollback, backup, observability, and post-release checks in `docs/operations.md` when those concerns exist.
- Put long-term direction in `docs/roadmap.md` only when the project has a real roadmap. It does not authorize work.
- Put the one active long-running execution plan in `PLANS.md` when planning authority is enabled.
- Put temporary progress and cross-session handoff state in `docs/work/current.md`. It records work but does not authorize new work.
- Put repository-wide working rules, verified commands, constraints, and completion checks in root `AGENTS.md`.
- When planning authority is enabled, put the execution precedence and roadmap prohibition in root `AGENTS.md` so they load without invoking this Skill again.
- When planning authority is enabled, put durable requirement-change routing and subagent authority limits in root `AGENTS.md`; keep the active classification, latest user decision, and task-local delegation details in `PLANS.md` or the delegation message.
- When execution-discipline signals exist, put continuation, bundled
  completion, priority basis, and delivery evidence in `PLANS.md`; put failed
  attempts, changed strategy, verified blockers, artifact identity, and
  repository state in `docs/work/current.md`.
- When Active local experience changes required behavior for this project, write the verified result into the project's canonical owner. Never make project correctness depend on a private user registry or Codex Memory.
- Add a nested `AGENTS.md` only when that subtree has materially different commands, constraints, ownership, or risk.
- Do not create `PLANS.md`, `docs/roadmap.md`, or `docs/work/current.md` as an inseparable bundle. Create only the artifacts justified by the project, but make their authority explicit whenever more than one exists.

Read `references/surface-guide.md` before adding any optional Codex surface. Never generate project-local model preferences, broad permissions, external integrations, hooks, command rules, or custom agents from a vague project description.

### 7. Keep instructions operational

Write `AGENTS.md` as an operational index, not a project encyclopedia:

- Reference authoritative docs instead of repeating them.
- Include commands only after verifying them.
- Express constraints as observable behavior.
- Put formatting and mechanical checks in tooling or CI when possible.
- Keep global rules at the root and local differences near their scope.
- Remove vague rules such as "write good code" or "follow best practices".
- Prefer observable acceptance criteria and validation evidence over instructions to "self-debate" or "be thorough".

Match the language of generated human-facing documents to the user's language unless the repository already has a clear documentation language policy.

### 8. Validate

Run:

```text
python "<skill-dir>/scripts/validate_project_context.py" <project-root> --profile <minimal|standard|advanced>
```

Then verify:

- every referenced path exists or is explicitly marked as planned
- every command has repository evidence or a successful run; treat validator warnings for command families it cannot prove mechanically as unresolved review items
- no `{{PLACEHOLDER}}` remains
- no concept has conflicting definitions across files
- no roadmap or checkpoint can be mistaken for the active execution plan
- versioned or non-canonical roadmap, plan, current-work, and handoff files have been inventoried instead of missed by exact-filename checks
- at most one plan is marked active with exclusive execution authority
- active planning fields do not conflict, and exactly one milestone is `in_progress` and matches `current_task_id`
- active-plan metadata, current task, exclusions, validation, and completion behavior are explicit
- bare continuation resolves to validate-then-advance, bundled work cannot be partially closed, and any delivery contract names its observable evidence
- the latest material requirement change has one canonical class and updated only the existing or justified authority owners it actually affects
- a new task can recover active work from repository artifacts, while a subagent receives an explicit bounded task packet
- a named handoff target was resolved before creating another task, and any claimed capability blocker has current evidence
- no subagent or task packet silently acquires roadmap, scope, or completion authority
- every applied local experience matches current repository evidence and project scope; Shadow experience remained verification-only
- no Candidate, Conflicted, Rolled-back, generated memory, private path, secret, or raw transcript became project guidance
- when experience learning was loaded, finalization produced a private receipt even when no eligible experience existed
- every promoted experience has user approval, forward-test evidence, and a regression test
- advanced surfaces have passed syntax checks plus a separate semantic review of permissions, side effects, trust boundaries, and disable/recovery behavior
- nested `AGENTS.md` files add local information instead of duplicating the root
- no secrets, personal absolute paths, or unsafe permission defaults were introduced
- durable project files do not hard-code the current repository's host-local absolute path
- when the solo-software delivery module is active, each lifecycle gate distinguishes evidence from assumptions, names blocking conditions, and routes durable conclusions to one canonical owner
- no lifecycle recommendation silently authorizes a Git commit, push, deployment, production migration, data deletion, purchase, or other external side effect
- relevant project tests or checks pass when implementation files changed

Treat validator warnings as review prompts, not automatic failures. Fix errors and explain any intentionally retained warning.

### 9. Report the result

Summarize:

- files created or updated
- assumptions made
- optional modules enabled and the evidence that justified each one
- advanced surfaces deliberately omitted
- validation performed
- decisions still requiring the user

When experience learning was loaded, run its `finalize` command before this report. Do not surface routine registry administration; mention only formal-promotion-ready items, unresolved quarantines that affect the result, or an audit trail the user requested.

Do not claim the project is fully configured when commands, deployment, security, or external integrations remain unverified.

## Composition Contract

This Skill remains complete when used alone. When the optional governance set is present, it accepts a compact envelope with `request_id`, `intent_status`, `evidence_refs`, `scope`, `next_action`, and `budget`; it does not accept raw transcripts as authority.

- `intent-alignment` may supply a clarified goal and explicit non-goals. Treat it as **Decided** only when the user or a canonical project file supports it; otherwise keep it **Assumed** or **Open**.
- `durable-context` may supply a verified resume package. Use its requirements and ledger hashes as continuity evidence, but keep this Skill's project-file ownership rules authoritative for generated artifacts.
- `diagnose`, `architecture-health`, and `tdd-loop` may supply findings or checks. Store durable conclusions in the canonical project owner; do not copy their working notes into `AGENTS.md`.
- `human-centered-reasoning-guard` may deny a write or external action. A denial is a boundary signal, not a request to weaken this Skill's project structure.
- `deliberate-project` is read-only and explicit-only. Its findings can inform an audit or decision record, but never authorize implementation.

When an optional Skill is absent, continue with the standalone workflow and record the missing capability as an explicit **Open** item only if it changes the result. Never create a second plan, ledger, or project authority to emulate a missing integration.

## Guardrails

- Do not generate every possible file.
- Do not create one `AGENTS.md` per folder.
- Do not copy product descriptions into `AGENTS.md`.
- Do not invent scripts, package commands, directory names, or technology choices.
- Do not add dependencies solely to support this context system.
- Do not store credentials or tokens in generated files.
- Do not enable full-access sandboxing or approval bypasses.
- Do not add MCP servers, hooks, rules, plugins, agents, or automations without a concrete use case and an explained trust boundary.
- Do not overwrite human-authored files without preserving their intent and showing the change.
- Do not turn a roadmap into an executable checklist or silently choose work from it.
- Do not assume a new task, fork, or subagent automatically knows the active objective, exclusions, acceptance criteria, or latest user decision.
- Do not let a subagent reclassify requirements, change plan authority, broaden scope, or claim whole-project completion. A formal task takeover uses the new-task handoff contract instead of a subagent packet.
- Do not treat Codex Memories as the source of required project or Skill behavior.
- Do not let Candidate, Conflicted, or Rolled-back experience influence another project; Shadow may suggest verification only.
- Do not capture raw transcripts, source code, client identifiers, repository paths, credentials, personal data, or long logs in the experience registry.
- Do not auto-edit this Skill, auto-commit, auto-push, or auto-publish an experience. The private registry may auto-promote to Active, but formal Skill promotion requires explicit user authorization and normal Skill validation.
- Do not grow the Skill for every correction. Keep project-specific lessons in the project, route conditional patterns to references, and use scripts or tests for mechanical failures.
- Do not force planning IDs, roadmaps, checkpoints, or strict governance onto projects that do not need them.
- Do not initialize Git, commit, push, deploy, or install packages unless the user requested that broader action.

## Reference routing

- Read `references/interview-and-profiles.md` for discovery questions, profile selection, and artifact criteria.
- Read `references/planning-authority.md` when long-running work, multiple plans, reprioritization, or plan confusion is present.
- Read `references/context-ownership-and-migration.md` when cross-session recovery, old-project takeover, competing context files, or historical research deduplication is present.
- Read `references/plan-navigation.md` when a validated active plan needs stable long-horizon route coordinates or continuity-parent recovery.
- Read `references/change-intake-and-agent-handoff.md` when requirements change during work or when a new task, fork, or subagent must continue the work.
- Read `references/execution-discipline.md` for long-running continuation,
  atomic completion, priority, blocker, retry, delivery, terminology,
  effective-state, or blast-radius signals.
- Read `references/experience-learning.md` when capturing, reviewing, applying, retiring, or promoting experience across projects.
- Read `references/solo-software-delivery.md` when validating a product problem, defining an MVP or first vertical slice, comparing reuse with custom implementation, assessing stage readiness, preparing a release, or deciding whether to continue, simplify, pivot, or stop.
- Read `references/change-review.md` for a named baseline, prior review record, live-tree drift, consequential evidence comparison, or namespaced review-completion reporting.
- Read `references/skill-design-principles.md` only when maintaining this Skill or applying its design principles to another Skill.
- Read `references/surface-guide.md` only when deciding where information belongs or whether advanced Codex surfaces are justified.
- Read `references/design-sources.md` only when maintaining this skill or explaining how its design relates to existing open-source approaches.
