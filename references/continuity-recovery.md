# Continuity Recovery Contract

Use this contract when a task continues after a new session, compaction, handoff, or a suspected context loss. It is intentionally small: the ledger stores indexes, status, and hashes, not a transcript.

## Recovery Package

The generated `handoff.md` and `resume` output carry one compact `CONTINUITY STATUS` package:

- current task, checkpoint, task ID, requirements revision/hash;
- current Git revision and `PLANS.md` hash when present;
- validated route coordinate, if the project has plan navigation;
- references to confirmed decisions, verified findings, open unknowns, and research receipts;
- one next action and a baseline comparison status.

The project-local ledger remains the authority. A compaction summary, old handoff, Obsidian note, MCP result, or model recollection is evidence to verify, never a replacement.

## Bounded Tiers

Follow the tiers in order and stop when the current task is actionable:

| Tier | Scope | Default |
| --- | --- | --- |
| 0 | current `requirements.md`, `handoff.md`, `task.md` | always |
| 1 | verified `findings.md`, active `decisions.md`, valid `PLANS.md` | when Tier 0 is insufficient |
| 2 | explicit, relevant change/history summaries | only for a named unresolved question |

Each retrieval has a maximum result count, character budget, and history count. Reaching a limit returns a bounded status and a next action. It must not launch another recovery agent, rebuild an index, or silently broaden the search.

## Missing and Conflict States

Use these states in read-only search or recovery reports:

- `FOUND`: the requested evidence is present and verified;
- `PARTIAL`: only part of the request is supported;
- `NOT_FOUND`: the bounded scope found no matching evidence;
- `CONFLICTED`: explicit sources disagree; do not choose by recency alone;
- `BLOCKED_UNCERTAINTY`: the missing item matters to a high-risk action;
- `LIKELY_LOST`: use only when an explicit audit proves the authoritative record is unavailable. Never infer it from an empty search.

Low-risk missing details may remain an explicit unknown while work continues. Missing migration, security, permission, ownership, supplier, data-loss, or irreversible-operation facts should block the action and request an exact source or human decision.

## Research Receipts

Record a small receipt in the `Research Receipts` part of `findings.md` only after research is verified:

```text
### Research Receipt: R-2026-001
- research_id: R-2026-001
- question: the exact question that was checked
- scope: sources and time boundary
- status: VALID | EXPIRED | CONFLICTED | SUPERSEDED
- sources: source references, not full documents
- conclusion: one bounded conclusion
- decision_ref: D-001 or none
- checked_at: 2026-08-18
- superseded_by: none
```

Before repeating research, look for a `VALID` receipt with the same question and scope. Reuse it when its sources are still within the stated time boundary; otherwise perform a local recheck. A conflicted or superseded receipt cannot authorize an automatic choice.

## Baseline Drift

At initialization and each verified checkpoint, record the baseline tuple `{git_revision, plans_hash, requirements_hash, requirements_revision}`. On resume, compare the current tuple with the recorded tuple. `CHANGED` means rebaseline and inspect the affected source; it does not mean the implementation is wrong. Do not proceed with a stale or unrecorded requirements hash.
