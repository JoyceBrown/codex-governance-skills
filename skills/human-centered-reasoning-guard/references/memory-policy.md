# Memory Policy

## Layers

1. **Task memory**: current goal, constraints, authorization, facts, unknowns, decisions, risks, and next action.
2. **Observation**: a minimal redacted fact about what happened. It is never automatically applied.
3. **Candidate experience**: an abstract trigger/action lesson backed by evidence but not yet trusted.
4. **Active principle**: a reusable lesson with scope, confidence, evidence, and review metadata.
5. **User preference**: an explicitly stated durable preference, separate from project rules and one-off requests.

Recommended storage is project-local `.agent-context/` for task state and user-local `$CODEX_HOME/ai-experience/` for global experience. When `CODEX_HOME` is unset, resolve it to the platform's default Codex directory. Project-scoped experience must include a stable `project_id` (prefer a repository remote hash, otherwise a normalized project-root hash). Keep the first implementation append-only JSONL. Add SQLite or semantic search only after retrieval cost is measured.

## Required Fields

Every experience should have:

```json
{
  "id": "stable-slug",
  "status": "candidate|active|superseded|expired",
  "trigger": "observable situation",
  "action": "reusable behavior",
  "scope": "project|global",
  "project_id": "required for project scope, null for global",
  "source": "manual|user-correction|verified-test|session-observation",
  "evidence": ["redacted evidence reference"],
  "confidence": 0.0,
  "counterexamples": [],
  "supersedes": null,
  "created_at": "ISO-8601",
  "review_at": "ISO-8601"
}
```

Do not store passwords, tokens, cookies, full private conversations, raw tool streams, full source files, or unnecessary absolute paths. Prefer identifiers, short hashes, and redacted summaries.

## Promotion and Conflict Rules

- One incident creates a `candidate`, never an `active` global rule.
- Explicit user correction or repeated independent evidence can raise confidence.
- Promotion from project to global requires the same principle in at least two projects, or explicit user approval.
- A current user instruction and current verified evidence override historical experience.
- A contradiction lowers confidence; it does not silently delete the old record. Mark the old rule `superseded` and record why.
- Decay unused or unreviewed rules. Expired rules remain auditable but are not injected.
- Retrieve only a small relevant set; never load the entire memory store into context.
- The retrieval path must filter by project scope before ranking. Global rules may be considered only after project-scoped candidates are checked.
- A candidate with empty evidence, missing project scope, or expired review date is not eligible for automatic use.

## What Counts as Learning

Good candidates are non-obvious, repeatable, transferable, and verified. Do not learn from a documentation lookup, a one-off typo, an unverified hypothesis, user frustration alone, or the model's own preference.

## Bounded Self-Improvement

```text
observe -> redact -> hypothesize -> verify -> candidate -> replay -> promote or reject
```

The skill may produce candidate records, but it must not rewrite its own core instructions, silently change global policy, or auto-install new skills.

Run `scripts/audit-experience-store.ps1` before retrieval in a long-running project or after a new promotion. The audit is read-only: it validates the append-only store, filters by project scope, reports due-for-review records and same-scope conflicts, and never silently expires or supersedes a rule. Resolve a conflict with `scripts/review-experience.ps1` using explicit evidence and a counterexample; only then should retrieval use the updated active record.
