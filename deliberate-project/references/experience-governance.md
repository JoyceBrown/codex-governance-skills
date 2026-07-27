# Governed Experience Catalog

Use this module to read reusable cross-project lessons before method routing and to write verified observations only after the inquiry report is stable. Current-case notes and project-specific prior findings remain separate; the catalog stores redacted reusable lessons, never raw project material.

## Contents

- [Authorization and boundary](#authorization-and-boundary)
- [Pre-inquiry read path](#pre-inquiry-read-path)
- [Required write gates](#required-write-gates)
- [Legal lifecycle](#legal-lifecycle)
- [Conflict resolution](#conflict-resolution)
- [Tool usage](#tool-usage)
- [Reporting](#reporting)

## Authorization and Boundary

Resolve the catalog root from the host config file selected by `DELIBERATE_PROJECT_EXPERIENCE_CONFIG` or the default `CODEX_HOME/deliberate-project-experience-root.txt`, then `AEGOS_SKILLS_EXPERIENCE_ROOT`. The config file contains exactly one existing absolute directory path. The automated CLI accepts no `--root` override. Configuration authorizes only `scripts/experience_catalog.py` to create or update the fixed `deliberate-project/experience.sqlite3` catalog beneath that root; it authorizes no other external write.

Only the primary agent may operate the catalog. Read-only operations may run after the case and focus profiles are stable and before method routing. Mutating operations may run only after the inquiry report is stable and only when the current request does not prohibit persistence or all writes. A configured root is an approved storage capability, not authority to override a current read-only instruction. Role agents return transient candidate material and never receive catalog write capability. If mutation is prohibited or the configured root is missing, invalid, or not writable, do not create a substitute location; continue without persistence and disclose the gap.

## Pre-inquiry Read Path

Run `load` without first running `refresh`. It returns only unexpired `Active` and `Shadow` lessons and never writes the database. The primary must still filter each returned lesson against the current domain, applicability scope, product or standard version, jurisdiction or market, time horizon, limitations, and recheck trigger.

- `Active` permits a defeasible routing hint or recurring-failure warning.
- `Shadow` permits only a method or verification suggestion.
- Catalog content never counts as current project evidence, never satisfies a finding dimension, and never changes a judgment without current-case verification.
- Record every lesson ID actually applied. Do not report loaded-but-unused lessons as applied.

Project-specific prior findings belong to the current project's re-review record, not this catalog. A current project observation overrides catalog experience within its verified scope.

## Required Write Gates

Before recording an observation, require:

- a redacted lesson claim containing no secret, private code, customer data, personal data, or raw case text;
- a stable case ID, at least one verified current-case evidence ID, a safe snapshot or fingerprint ID, a named verification method, and at least one traceable non-sensitive source locator;
- explicit applicability scope, version scope, jurisdiction or market, expiry date, recheck trigger, and limitations;
- completed privacy and licensing review;
- an outcome that was actually observed rather than a speculative improvement.

The CLI stores these attestations and exposes them through `show`. It cannot determine natural-language truth by itself; the primary remains responsible for establishing that the referenced evidence exists, entails the observation, and is safe to persist. Do not store hidden reasoning, role transcripts, credentials, absolute private project paths, or copied copyrighted content. Prefer hashes, public locators, or redacted local source IDs.

## Legal Lifecycle

The tool enforces event validity and legal transitions:

1. A new lesson begins in `Candidate` and accepts only verified `candidate` observations. Two distinct cases with non-overlapping declared source lineages move it to `Shadow`. A verified high-risk workflow fix may enter `Shadow` after one candidate case but never `Active` directly.
2. `Shadow` accepts verified `shadow-benefit`, `shadow-regression`, or `conflict` observations. Only benefits recorded while the lesson was already `Shadow`, from two distinct cases with non-overlapping declared source lineages, move it to `Active`.
3. `Active` accepts only verified regression or conflict observations, plus an explicit retirement operation.
4. A verified regression moves `Shadow` or `Active` to `Rolled-back`.
5. `Expired`, `Deprecated`, and `Rolled-back` reject ordinary observations and cannot be silently revived.
6. `Conflicted` rejects ordinary observations until an explicit conflict-resolution operation restores or retires the affected lessons.
7. A duplicate lesson/case/outcome tuple is idempotent: it reports `duplicate=true`, makes no change, and does not update a high-risk flag or gate count.
8. Read operations compute expiry without writing. `load` excludes expired lessons immediately. `refresh` exists only to persist expiry transitions in history.

Different case IDs are necessary but not sufficient for independence. Observations that share any declared source locator belong to the same lineage component and receive one promotion credit. Mirrors, repeated fixtures, multiple URLs from one publisher, or evidence derived from the same upstream material must declare that shared lineage; renaming a source or evidence ID to evade this gate violates the catalog contract.

Every accepted transition is appended inside the same database transaction. Version 1 catalogs migrate to version 2 without losing lessons or transition history. Migrated observations are labeled `Legacy-attested`: version 1 required privacy and licensing flags but did not retain the complete evidence attestation now required. They preserve existing status but do not count toward new promotion gates.

## Conflict Resolution

Record a true conflict only between existing `Shadow` or `Active` lessons whose claims are materially incompatible within the same applicable scope. The conflict observation is stored for both lessons, and both become `Conflicted`.

Resolve the pair with verified stronger evidence using exactly one action:

- `keep-first`: restore the first lesson's pre-conflict status and deprecate the second as superseded;
- `keep-second`: restore the second lesson's pre-conflict status and deprecate the first;
- `retire-both`: deprecate both lessons;
- `continue-isolation`: preserve both as `Conflicted` while recording why evidence remains insufficient.

The tool records the action, evidence IDs, source lineage, snapshot ID, verification method, reason, and resulting states. It does not decide whether natural-language claims conflict or which lesson should survive.

## Tool Usage

Resolve, inspect, and load without writing:

```text
python scripts/experience_catalog.py resolve
python scripts/experience_catalog.py doctor
python scripts/experience_catalog.py load
python scripts/experience_catalog.py list
python scripts/experience_catalog.py show --lesson-id <id>
```

Record a verified reusable observation after the report is stable:

```text
python scripts/experience_catalog.py observe --case-id <case> --claim <redacted-lesson> --scope <scope> --version-scope <versions> --jurisdiction <market-or-na> --expires-at <YYYY-MM-DD> --recheck-trigger <trigger> --limitations <limits> --source <safe-locator> --evidence-id <verified-id> --snapshot-id <safe-snapshot-id> --verification-method <method> --outcome candidate --verified --privacy-reviewed --license-reviewed
```

Use `shadow-benefit`, `shadow-regression`, or `conflict` only in a state that accepts that outcome. A conflict also requires `--related-lesson-id`. Use `--high-risk-fix` only with a verified candidate observation for a demonstrated high-risk workflow defect.

Resolve a conflict with `resolve-conflict --lesson-id <first> --related-lesson-id <second> --action <action>` plus the same source, evidence, snapshot, verification, privacy, and licensing fields. Use `retire --target Deprecated|Rolled-back --reason <redacted-reason>` for an allowed explicit retirement. Use `migrate` for a schema upgrade and `refresh` only when persisted expiry history is needed.

The tool emits a JSON receipt. Treat a nonzero exit as no catalog change. Do not retry with a broader path, weaker evidence gate, different event label, or illegal state transition.

## Reporting

Always disclose:

- whether read or write operations were attempted and the resolved catalog path or failure reason;
- lesson IDs loaded and the subset actually applied;
- lesson ID, before/after/effective status, case ID, outcome, duplicate/change result, and evidence IDs for a write;
- whether a conflict, resolution, expiry, rollback, migration, or retirement occurred;
- any `Legacy-attested` record used only as a Shadow suggestion.

Catalog success does not upgrade inquiry evidence, safety assurance, response class, technical change state, stakeholder response, or completion state.
