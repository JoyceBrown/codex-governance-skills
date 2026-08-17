# Context Ownership And Migration

Use this reference when an existing project has several plans, handoffs, requirement files, old research notes, or a new session must continue work without copying the whole history.

## One Owner Per Fact

| Artifact | Canonical responsibility | Allowed in other artifacts |
| --- | --- | --- |
| `PLANS.md` | one active execution route, current task, scope, milestones, completion semantics | links and read-only route coordinates |
| `requirements.md` | current objective, acceptance, constraints, and implementation details | compact hash/reference in checkpoints |
| `decisions.md` | durable decisions, alternatives, evidence, reversal trigger | decision ID links |
| `findings.md` | verified facts, command results, source locations, bounded research receipts | finding/receipt ID links |
| `handoff.md` | generated checkpoint, current evidence, risks, and one next action | generated continuity index |
| `task.md` or `docs/work/current.md` | non-authoritative execution notes and progress | links to the active plan |

Do not copy the same requirement, decision, or research conclusion into every file. If a reader needs the detail, link to its owner and carry only its ID, status, and hash in the handoff.

## Migration Classification

For each old plan, requirement, handoff, status file, or research note, classify it before using it:

| Classification | Meaning | Action |
| --- | --- | --- |
| `KEEP` | still current and owned by the correct file | retain and link |
| `UPDATE` | useful but its owner or wording is stale | move the minimum fact to the owner and record why |
| `ARCHIVE` | historical evidence with no current authority | preserve out of the active path; never select work from it |
| `SUPERSEDE` | replaced by a newer verified decision or plan | link the replacement and mark the old item |
| `CONFLICT` | two sources make incompatible current claims | stop automatic selection and resolve with evidence/human decision |
| `UNKNOWN` | relevance, owner, or truth cannot be established | keep out of execution; record as an open question |

Do not delete old material merely to make the tree look clean. Archive or mark it with the reason and replacement reference. A filename, timestamp, or model-generated summary is not enough evidence to upgrade `UNKNOWN` into a project fact.

## Cold-Start Migration

Use this order for a project that must survive a new Codex session:

1. Audit the current tree read-only and identify all competing authority candidates.
2. Confirm the project root, repository revision, active plan owner, and protected boundaries.
3. Create or repair the single active `PLANS.md` and current `requirements.md`.
4. Move only verified decisions, findings, and research receipts to their canonical owners.
5. Generate the current handoff/checkpoint with baseline hashes and one next action.
6. Mark old artifacts with the classification above and retain their audit trail.
7. Run a cold-start recovery test from a fresh task: verify the current plan is selected, old work is not repeated, and unresolved facts remain unknown.

The migration is complete only when a fresh session can reconstruct the active baseline from current files without reading the old conversation or guessing a missing consensus.
