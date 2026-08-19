# Context Failure Modes

## Goal Drift

Symptom: the agent starts solving a nearby problem or repeats exploration.

Response: read `task.md` and `handoff.md`, identify the active acceptance check, and checkpoint before changing direction.

## Stale Or False Memory

Symptom: a prior decision conflicts with current code, tests, user direction, or external state.

Response: treat the ledger entry as a lead, verify against the current authority, and append the correction with evidence. Do not silently overwrite the prior decision.

## Context Flooding

Symptom: large plans, transcripts, graph exports, or tool output dominate the prompt.

Response: load the resume brief first, then retrieve only the active phase and relevant files. Store large artifacts by path and a short conclusion rather than copying them into the ledger.

## Interrupted Action

Symptom: a network request, write, publish, payment, or command may have completed before interruption.

Response: record the uncertainty, inspect authoritative state, and do not retry the action until completion is known.

## Parallel Writer Conflict

Symptom: multiple agents update the same plan and state diverges.

Response: assign one parent as ledger writer. Child agents return concise evidence with paths and commands; the parent records only verified conclusions.

## Scope Leakage

Symptom: personal facts or information from another project affects the current task.

Response: keep ledgers project-local by default. Use an explicit external memory scope only when the user authorizes it, and label the source scope in the retrieved result.

## Objective Collision

Symptom: a new objective arrives while a different ledger is active or blocked.

Response: never resume the old objective silently. Classify the new request as a scope revision or a distinct task switch, then record or archive before continuing.

## Unrecorded Requirement Change

Symptom: `requirements.md` differs from its recorded hash or a checkpoint is attempted without a requirement-change event.

Response: reject the checkpoint, capture the full current requirement snapshot as a new revision, and reconcile before work continues.

## Superseded Retrieval

Symptom: an Obsidian search result originates from `历史/` or has `superseded`, `needs-review`, or `observed` status.

Response: exclude it from default retrieval. Include it only for explicit historical or diagnostic work, and never treat it as the current project route.

## Detail Revision Without Current State

Symptom: a detail change appears in `changes.jsonl` but not in the current requirements snapshot.

Response: merge the detail into `Current Details` before completing the revision. Never rely on the recent-change window as the only copy of an active detail.

## Resume Budget Overflow

Symptom: full requirement snapshots or long event objects make the resume output exceed its requested character budget.

Response: inject only compact event metadata and allocate bounded sections. Retrieve full snapshots only from disk for explicit historical analysis.

## Recovery Search Loop

Symptom: an empty result triggers new keywords, a new index, another agent, or progressively broader history searches.

Response: follow the fixed recovery tiers in `continuity-recovery.md`, return `NOT_FOUND` with searched scope and consumed budget, and stop. Escalate to `BLOCKED_UNCERTAINTY` only when the missing fact affects a high-risk action.

## Invented Historical Consensus

Symptom: fragments from code, old notes, or model memory are rewritten as a prior decision that cannot be found.

Response: preserve the gap as `NOT_FOUND` or an explicit unknown. A necessary reconstruction must be labeled `RECONSTRUCTED_HYPOTHESIS` and cannot be recorded as a historical decision without human confirmation.

## Repeated Research

Symptom: a new session repeats an already verified vendor, architecture, or policy investigation.

Response: check a matching Research Receipt first. Reuse a current receipt, recheck only expired scope, and stop automatic selection when receipts or sources conflict.

## Vault Body Drift

Symptom: the project overview, current requirements, revision snapshot, or registry has matching metadata but different content.

Response: verify generated-page content hashes and the shared canonical requirements hash. Exclude any invalid projection from default search and regenerate it from the project ledger.
