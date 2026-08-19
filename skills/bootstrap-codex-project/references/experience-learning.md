# Experience learning and promotion

Use this module when the Skill has a private learning registry, the user asks it to remember or improve, or a run produces real reusable friction.

## Goal and authority boundary

Improve later project work without asking the user to administer individual lessons and without turning one anecdote into a universal rule.

Use three layers:

```text
Private registry
    -> automatic sanitized capture, evidence audit, Shadow, Active, quarantine, rollback

Project authority
    -> verified requirements in that project's docs, code, tests, or active plan

Version-controlled Skill
    -> curated behavior changed and published only with explicit user authorization
```

The private lifecycle is automatic. It may change local registry status, but it must not edit this Skill, commit, push, publish, or override project evidence. Codex Memories are optional recall and never the only owner of required behavior.

## Private registry

Resolve `<skill-dir>` to the directory containing `SKILL.md`. The deterministic tool is:

```text
python "<skill-dir>/scripts/experience_registry.py"
```

The default store is `<CODEX_HOME>/learning/bootstrap-codex-project/`, or the normal user Codex home when `CODEX_HOME` is unset. It is private local state and must not enter a public repository.

Capture modes:

- `auto_sanitized` is the default. Capture only generalized structured summaries after real failures or user corrections.
- `ask` requires current confirmation through `--confirm-capture`.
- `off` rejects capture.

This is not a background monitor. It runs only when this Skill is active. Automatic redaction is defense in depth, not permission to store raw transcripts, source code, client identifiers, repository paths, credentials, personal data, or long logs.

## Capture eligibility

Capture only when at least one concrete signal exists:

- the user corrected the Skill's classification, decision, or output
- Codex repeated a mistake that existing rules should have prevented
- a generated artifact caused real confusion or unnecessary ceremony
- a validator missed a reproduced structural error
- a project exposed a reusable boundary or failure mode
- the user explicitly asked the Skill to remember the case

Record the generalized problem, observed failure, preferred response, scope, matching signals, sanitized evidence summaries, severity, and reproduction state. The tool deduplicates equivalent records, counts occurrences, and stores one-way project fingerprints rather than project paths.

Do not manufacture a lesson merely because a run completed. A final receipt may say `no-eligible-experience`.

## Automatic lifecycle

The registry uses these states:

```text
candidate
    -> shadow       enough independent or severe reproduced evidence
    -> conflicted   a contradiction reaches a reusable state
    -> rejected     explicit exceptional review

shadow
    -> active       benefits observed in two independent projects
    -> conflicted   direct or observed contradiction
    -> rolled_back  observed regression

active
    -> conflicted   contradiction is quarantined
    -> rolled_back  observed regression
    -> promoted     formal Skill update passed every gate and was authorized
```

`retired`, `rejected`, `rolled_back`, and `promoted` records are not automatically reactivated. Schema-v1 `accepted_local` records migrate to `active` while preserving review and promotion metadata.

Automatic gates:

1. `candidate -> shadow` after evidence from at least two independent project fingerprints, or after a reproduced high/critical failure with at least two distinct evidence summaries.
2. Shadow advice is `verify_only`: use it to check a hypothesis or method, never as established project guidance.
3. Record a `shadow-benefit` only when repository evidence shows the Shadow suggestion helped. Two distinct project fingerprints promote it to `active`.
4. `active` advice is `apply_advisory`: it still requires matching scope, signals, current repository evidence, and the latest user instruction.
5. A `regression` outcome automatically moves Shadow or Active experience to `rolled_back`.
6. A direct or observed contradiction moves reusable local patterns to `conflicted`. Do not resolve semantic ambiguity by recency or occurrence count.
7. A local conflict with `promoted` experience quarantines the local record and never overrides the version-controlled Skill rule.

The capture and outcome commands run the deterministic audit immediately. `audit` safely rechecks every record and persists schema upgrades; repeated audits do not repeat a completed transition.

## Observe outcomes

Record only outcomes supported by the current project's evidence:

```text
python "<skill-dir>/scripts/experience_registry.py" observe <pattern-id> --kind shadow-benefit --summary "<sanitized observed benefit>" --project-root <project-root>

python "<skill-dir>/scripts/experience_registry.py" observe <pattern-id> --kind regression --summary "<sanitized regression>" --project-root <project-root>

python "<skill-dir>/scripts/experience_registry.py" observe <pattern-id> --kind conflict --summary "<sanitized contradiction>" --project-root <project-root>
```

Equivalent outcomes are idempotent. `shadow-benefit` requires a project root so one project cannot masquerade as independent validation.

## Apply local experience

After identifying the project type and concrete risk signals, query relevant experience:

```text
python "<skill-dir>/scripts/experience_registry.py" relevant --project-root <project-root> --project-type <type> --signal <signal>
```

For every result:

1. Respect `use_mode`: Shadow is verification-only; Active is advisory.
2. Confirm the scope and signals against current repository evidence.
3. Ignore it when it conflicts with the latest user instruction or authoritative project facts.
4. Apply the smallest relevant adjustment.
5. Put required project behavior in that project's authoritative files or tests.
6. Do not expose internal IDs unless the user asks for the audit trail.

Promoted records are excluded because their behavior is already version-controlled. Conflicted and rolled-back records are never recommendations.

## Mandatory end-of-run finalization

At the end of a run that loaded this module, execute:

```text
python "<skill-dir>/scripts/experience_registry.py" finalize --run-summary "<short sanitized result>"
```

Finalization audits all pending records and writes a private receipt with one outcome:

- `lifecycle-updated`
- `formal-promotion-ready`
- `attention-quarantined`
- `evidence-pending`
- `no-eligible-experience`

Do not ask the user to inspect or decide each record. Report only a compact batch when formal Skill candidates are ready, a conflict cannot be safely resolved, or the user requests the audit trail.

## Promote into the Skill

Private `active` status is not formal Skill promotion. Formal promotion requires all of these:

- the record is `active`, is not project-specific, and has observable matching signals
- independent generalization evidence exists
- the proposed rule states both its positive and negative trigger boundaries
- no private detail is needed to understand it
- representative forward tests and counterexamples pass
- regression tests pass
- the user explicitly authorizes the Skill update and any publication

`assess <pattern-id>` checks mechanical readiness only. It never grants permission. `mark-promoted` additionally requires `--user-approved`, a meaningful approval note, targets, and passed forward and regression evidence.

Choose the smallest target: recurring decisions in `SKILL.md`, conditional guidance in `references/`, repeated structures in `assets/templates/`, and deterministic checks in `scripts/` plus tests. Keep one-project rules in that project.

Never auto-edit `SKILL.md`, auto-commit, auto-push, or auto-publish from a local record. Formal promotion is the single remaining user authorization boundary.

## Exceptional manual controls

Normal use is automatic. `review` remains only for recovery, explicit rejection or retirement, and evidence-based resolution of a quarantined contradiction. A replacement must name every superseded local record. It cannot supersede `promoted` experience.

When several items need attention, batch them in plain language. Compare source quality, current repository evidence, platform version, applicability, causality, and observed outcomes; never ask the user to manage registry fields one by one.
