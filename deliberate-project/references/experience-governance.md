# Governed Experience Catalog

Use this module only after the inquiry report is stable. Current-case notes remain transient; the catalog stores redacted reusable lessons, never raw project material.

## Contents

- [Authorization and boundary](#authorization-and-boundary)
- [Required gates](#required-gates)
- [Automatic lifecycle](#automatic-lifecycle)
- [Conflict and rollback](#conflict-and-rollback)
- [Tool usage](#tool-usage)
- [Reporting](#reporting)

## Authorization and Boundary

Resolve the catalog root from `--root`, then the host config file selected by `DELIBERATE_PROJECT_EXPERIENCE_CONFIG` or the default `CODEX_HOME/deliberate-project-experience-root.txt`, then `AEGOS_SKILLS_EXPERIENCE_ROOT`. The config file contains exactly one existing absolute directory path. Configuration of that root is standing authorization only for `scripts/experience_catalog.py` to create or update the fixed `deliberate-project/experience.sqlite3` catalog beneath it. It does not authorize any other external write.

Only the primary agent may operate the catalog, after the user-facing inquiry is stable. Role agents return transient candidate material and never receive catalog write capability. If the root is missing, not a directory, outside the configured boundary, or not writable, do not create a substitute location; keep the candidate transient and disclose the gap.

## Required Gates

Before recording an observation, require:

- a redacted lesson claim containing no secret, private code, customer data, personal data, or raw case text;
- a stable case ID and at least one traceable, non-sensitive evidence locator;
- explicit applicability scope, version scope, jurisdiction or market, expiry date, recheck trigger, and limitations;
- completed privacy and licensing review;
- an outcome that was actually observed, not a speculative improvement.

Do not store hidden reasoning, role transcripts, credentials, absolute private project paths, or copied copyrighted source content. Prefer hashes, public locators, or redacted local source IDs.

## Automatic Lifecycle

The tool applies these bounded transitions:

1. A first eligible observation creates `Candidate`.
2. The same lesson observed in two independent case IDs moves to `Shadow`. A verified high-risk workflow fix may enter `Shadow` after one case but never `Active` directly.
3. A `Shadow` lesson requires beneficial shadow outcomes in two independent later cases to move to `Active`.
4. Run `refresh` before catalog use; lessons past their declared expiry move to `Expired` transactionally.
5. `Shadow` lessons may suggest a method or warning but cannot alter findings or judgments. `Active` lessons remain defeasible hints; current project evidence overrides them.

Repeated observations from the same case do not increase a gate count. Every transition is appended to the transition history inside the same database transaction.

## Conflict and Rollback

- Record a true conflict with the conflicting lesson ID. The tool marks both lessons `Conflicted`; neither may drive routing until resolved with stronger applicable evidence.
- A verified shadow regression moves `Shadow` or `Active` to `Rolled-back` and preserves the prior history.
- Use `Deprecated` for a lesson intentionally retired while still historically traceable.
- Do not silently edit a lesson's claim or scope. A changed meaning creates a different stable lesson ID and may reference the prior lesson as superseded evidence.

The tool does not decide whether two natural-language claims conflict. The primary must make that evidence-backed classification and supply the related lesson ID.

## Tool Usage

Resolve and inspect without writing:

```text
python scripts/experience_catalog.py resolve
python scripts/experience_catalog.py refresh
python scripts/experience_catalog.py doctor
python scripts/experience_catalog.py list
python scripts/experience_catalog.py show --lesson-id <id>
```

Record a reusable observation:

```text
python scripts/experience_catalog.py observe --case-id <case> --claim <redacted-lesson> --scope <scope> --version-scope <versions> --jurisdiction <market-or-na> --expires-at <YYYY-MM-DD> --recheck-trigger <trigger> --limitations <limits> --source <safe-locator> --outcome candidate --privacy-reviewed --license-reviewed
```

Use `--outcome shadow-benefit`, `shadow-regression`, or `conflict` only when that result was observed. A conflict requires `--related-lesson-id`. Use `--high-risk-fix` only for a verified high-risk workflow defect. Use `retire --target Deprecated|Rolled-back --reason <reason>` for an explicit retirement.

The tool emits a JSON receipt. Treat a nonzero exit as no catalog change and report the error without retrying with a broader path or weaker gate.

## Reporting

Always disclose:

- whether a catalog operation was attempted;
- resolved catalog path or why resolution failed;
- lesson ID and before/after status;
- case ID and outcome recorded;
- whether a conflict, expiry, or rollback occurred.

Catalog success does not upgrade inquiry evidence, safety assurance, or completion state.
