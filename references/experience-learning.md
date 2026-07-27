# Experience learning and promotion

Use this module when the user asks the Skill to remember a lesson, improve from project experience, review recurring failures, or promote a local lesson into the public Skill.

## Contents

- [Goal](#goal)
- [Private registry](#private-registry)
- [Capture rule](#capture-rule)
- [Review before reuse](#review-before-reuse)
- [Resolve old and new conflicts](#resolve-old-and-new-conflicts)
- [Apply accepted local patterns](#apply-accepted-local-patterns)
- [Promote into the Skill](#promote-into-the-skill)
- [Anti-drift rules](#anti-drift-rules)
- [Periodic maintenance](#periodic-maintenance)

## Goal

Make future project bootstraps better without turning memory, one project's preferences, or an unverified anecdote into a universal rule.

Use three layers:

```text
Codex Memories
    -> optional recall; never the only source for required behavior

Private experience registry
    -> structured, sanitized candidates and locally accepted patterns

Skill rules, references, templates, scripts, and tests
    -> curated behavior that passed promotion review
```

Project requirements still belong in that project's `AGENTS.md`, documentation, code, tests, or active plan. Do not make a project depend on the private registry.

## Private registry

Resolve `<skill-dir>` to the directory containing `SKILL.md`. The deterministic registry tool is:

```text
python "<skill-dir>/scripts/experience_registry.py"
```

By default it stores generated state under:

```text
<CODEX_HOME>/learning/bootstrap-codex-project/
```

When `CODEX_HOME` is unset, use the normal user Codex home. The store is private local state and is never part of the public Skill repository. The tool uses private file permissions where the operating system supports them and atomic replacement for records. This reduces accidental exposure and partial writes; it does not make a shared or compromised user account confidential.

Supported capture modes:

- `off`: never propose or save experience candidates.
- `ask`: detect reusable friction and ask before saving a sanitized candidate. This is the default.
- `auto_sanitized`: during runs that use this Skill, automatically save only structured, sanitized candidates after a real failure or user correction; still require review before use.

The CLI enforces the mode. `off` rejects capture. In `ask`, pass `--confirm-capture` only after the current user has agreed to save that candidate.

This is not a background monitor. It does not observe unrelated development tasks where the Skill is not active.

Read the current mode:

```text
python "<skill-dir>/scripts/experience_registry.py" config
```

Change it only when the user requests:

```text
python "<skill-dir>/scripts/experience_registry.py" configure --capture-mode ask
```

## Capture rule

Capture only when at least one concrete signal exists:

- the user corrected the Skill's project classification or output
- Codex repeated a mistake that existing rules should have prevented
- a generated file caused real confusion or unnecessary ceremony
- a validator missed a reproducible structural error
- a project exposed a new, reusable boundary or failure mode
- the user explicitly asks to remember or learn from the case

Do not capture generic preferences, speculation, praise, raw transcripts, source code, client names, repository paths, credentials, personal data, or long logs.

Automatic redaction covers common tokens, credentials in URLs, secret assignments, private-key blocks, email addresses, and user-home paths, but cannot reliably detect every client name or sensitive business fact. Always write a generalized summary; never use redaction as permission to submit raw material. Malformed records fail closed instead of being silently ignored.

Record:

- the problem in general terms
- the observed failure
- the preferred behavior
- scope: `project_specific`, `project_family`, or `cross_project`
- matching project types and observable signals
- sanitized evidence summaries
- severity and whether the failure was reproduced

`project_specific` requires a project root and is deduplicated only inside that project. `project_family` requires a project type. Reusable scopes require at least one observable matching signal, so an empty-signal record cannot match every project.

The tool deduplicates equivalent candidates, increments occurrence counts, and stores only a one-way project fingerprint instead of the project path.

## Review before reuse

A new record has `status: candidate` and cannot influence another project.

Review it with the user:

- `accept` -> `accepted_local`; it may be suggested only when scope and signals match.
- `reject` -> `rejected`; keep it as evidence that the idea was considered.
- `retire` -> `retired`; stop applying an older accepted pattern.

Transitions are one-way: only a candidate can be accepted or rejected, and only an accepted or promoted record can be retired. Retired and rejected records cannot be reactivated by changing a review decision.

Never auto-accept a candidate. When several candidates are pending, summarize them in plain language instead of asking the user to understand registry fields.

## Resolve old and new conflicts

When a new candidate describes the same normalized problem in the same scope, overlaps the same project or matching signals, and recommends a different response, the tool records `conflicts_with`. This catches direct contradictions; it is not semantic proof that differently worded lessons agree.

Do not use recency alone. Compare source quality, current repository evidence, platform version, applicability, and observed outcomes. Reject the weaker candidate, or accept the replacement with `--supersedes <old-pattern-id>`. Acceptance is blocked until every conflicting `accepted_local` record is explicitly superseded; those older records become `retired` and point to the replacement. A local review cannot supersede a `promoted` record, because the version-controlled Skill and its tests must be changed through the full promotion process.

## Apply accepted local patterns

After inspecting a new project and identifying its type and risk signals, query relevant accepted patterns:

```text
python "<skill-dir>/scripts/experience_registry.py" relevant --project-root <project-root> --project-type <type> --signal <signal>
```

Use the result as advisory context:

1. Check that the current repository evidence actually matches.
2. Ignore any pattern that conflicts with the latest user instruction or authoritative project facts.
3. Apply only the smallest relevant adjustment.
4. Put required behavior into this project's authoritative files or tests.
5. Do not mention internal IDs unless the user asks for the learning audit trail.

`project_specific` patterns apply only to the same project fingerprint. `project_family` patterns require a matching project type and signal. `cross_project` patterns always require matching signals.

## Promote into the Skill

Promotion means changing the version-controlled Skill, not merely accepting a local candidate.

Require all of these gates:

- the candidate is already `accepted_local`
- it is not `project_specific`
- it has observable matching signals
- it occurred in at least two independent projects, or it is a reproduced high/critical failure with at least two evidence summaries
- the proposed rule states when it applies and when it does not
- no private project details are needed to understand it
- realistic forward tests cover representative projects and counterexamples
- regression tests protect existing behavior
- the user explicitly authorizes the Skill update and any GitHub publication

Run `assess <pattern-id>` to inspect the mechanical gates. The result never constitutes approval.

Choose the smallest promotion target:

| Learned behavior | Promotion target |
| --- | --- |
| Core decision used in nearly every run | `SKILL.md` |
| Conditional project-family guidance | a routed file under `references/` |
| Repeated output structure | `assets/templates/` |
| Deterministic detection or enforcement | `scripts/` plus tests |
| One project's rule | that project's `AGENTS.md`, docs, code, or tests; do not promote |

After implementation, forward testing, regression testing, local Skill synchronization, and user-authorized publication, mark the record promoted with its target artifacts and regression tests. Promoted records are excluded from local recommendations to avoid injecting duplicate context.

The `mark-promoted` command requires `--user-approved`, an approval note that names the approved change, at least one `--forward-test`, and at least one `--regression-test`. Every recorded test item must include a result such as `passed` or `exit=0`; filenames alone are not test evidence. Set `--user-approved` only from explicit authorization in the current task.

## Anti-drift rules

- Do not let Codex Memories silently change Skill behavior.
- Do not read or edit generated memory files as the Skill's primary control surface.
- Do not auto-edit `SKILL.md`, auto-commit, auto-push, or auto-publish from a captured candidate.
- Do not promote because a request sounds broadly useful.
- Do not use occurrence count without checking independent projects and causality.
- Do not solve every lesson with another instruction; prefer tests or scripts for mechanically detectable failures.
- Do not grow `SKILL.md` indefinitely. Merge overlapping rules, retire obsolete guidance, and keep conditional detail in routed references.
- Do not preserve a pattern forever. Retire it when platform behavior, tooling, or project evidence changes.

## Periodic maintenance

When the user asks for a learning review:

1. List pending candidates and accepted local patterns.
2. Merge semantic duplicates without deleting evidence.
3. Reject project-specific noise misclassified as general.
4. Test whether older patterns still match current Codex behavior.
5. Promote only candidates that pass all gates.
6. Retire stale or harmful patterns.
7. Report what changed, what stayed local, and why.
