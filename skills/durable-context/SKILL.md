---
name: durable-context
description: Automatically preserve and restore high-signal task context for complex, long-running, interrupted, or multi-session work. Invoke implicitly, without waiting for the user to name this skill, when a task has multiple phases, many tool calls, context-window pressure, compaction, a pause-and-continue cycle, important decisions, or a large codebase that needs targeted retrieval. Keep lifecycle operations internal and never ask the user to manage the ledger.
---

# Durable Context

Maintain a small project-scoped context ledger as durable working memory. Decide when to use it from the task state; do not make the user choose a mode, remember a command, or explicitly invoke this skill. Keep the active prompt small and put only verified, reusable state on disk.

## Automatic Routing

Use this internal routing without exposing it as a user workflow:

| Situation | Automatic action |
| --- | --- |
| Simple question or small self-contained edit | Do not create or touch a ledger. |
| New task with several dependent steps, research, code changes, or likely interruption | Start the ledger automatically. If one does not exist, initialize it with the current objective. |
| A proposed objective differs from an active or blocked ledger | Do not resume silently. Classify it internally as either a scope revision of the same task or a distinct task switch; record or archive before continuing. |
| Continuation after compaction, a new session, or the user asking to continue | Validate the existing ledger and load the compact resume brief before inspecting or editing anything. |
| Meaningful phase completed, important decision verified, test result obtained, risky external action, context pressure, or the user asking to pause | Record a concise checkpoint automatically. |
| Handoff, pause, or final completion | Verify the ledger, write the final state, and leave one concrete next action or a completed status. |

Use the bundled lifecycle helper through its single internal automatic entry point. The older low-level operations remain implementation details for compatibility and diagnostics; do not present them as commands the user should learn or run.

When the user-level Codex hooks are enabled, `SessionStart` validates and restores an existing project ledger. The default template does not register `UserPromptSubmit`; if an installation enables it for diagnostics, a lexical requirement hint produces privacy-safe telemetry only and never creates a write gate. `PreToolUse` allows normal source edits, diagnostics, shell commands, and UI tools regardless of ledger drift; it denies only an explicit direct file write inside the authoritative `.agent-context` directory, which must use the trusted lifecycle helper. Project, Git, and plan drift are observer signals, not workbench gates. `PreCompact` and `PostCompact` record ledger problems without stopping compaction, while `SessionStart(source=compact)` compares task ID, checkpoint, revision, and requirements hash across compaction. `Stop` reports ledger bookkeeping inconsistencies as an advisory without requesting continuation; only an incomplete ledger transaction may request one bounded continuation. Hook failures degrade to a bounded warning and fail open for unrelated project work; they must not bypass Codex hook trust.

Treat Hook telemetry as diagnostic data only. It may record the event, outcome, reason code, latency, hashed session/turn identifiers, tool name, task ID, checkpoint, revision, and requirements hash. Never record the raw prompt, tool arguments, transcript, document content, or credentials. Keep telemetry bounded and outside the authoritative ledger hash chain.

Store the ledger in `<project>/.agent-context/` by default. Keep it out of version control unless the user asks to share it with the team. Treat it as task state, not a transcript, personal memory store, or credential store. Keep one writer: the parent agent owns the ledger; parallel agents return evidence only.

## Start Or Resume Internally

1. Let the automatic entry point inspect whether `.agent-context/` exists and initialize or resume as appropriate.
2. Read `requirements.md`, `task.md`, and `handoff.md` first, then the recent `changes.jsonl` entries and only the decisions or findings relevant to the active phase.
3. Run the internal consistency check. If it reports a warning or conflict, reconcile it before following an older route, acceptance standard, or decision.
4. Read current repository rules, source, tests, and external state. Do not trust a stale handoff over current files, test output, or user instructions.
5. If a previous action may have changed external state, inspect authoritative state before retrying it.

For a new session, compaction, handoff, or suspected context loss, read [continuity-recovery.md](references/continuity-recovery.md). Restore the compact `CONTINUITY STATUS` package first; compare its Git, plan, and requirements baseline before following the old next action.

## Maintain The Ledger Internally

Use each file for one purpose only:

| File | Record | Do not record |
| --- | --- | --- |
| `task.md` | non-authoritative execution plan and execution notes | objective, acceptance, route, constraints, or implementation requirements |
| `requirements.md` | the single current objective, acceptance standard, route, details, and revision | historical alternatives or multiple active standards |
| `findings.md` | verified facts, command results, source locations | assumptions presented as facts |
| `decisions.md` | decision, alternatives, evidence, reversal trigger | unreviewed preferences |
| `handoff.md` | generated latest checkpoint and next action | manually maintained long notes |
| `history.jsonl` | timestamped checkpoint audit trail | secrets, raw prompts, full tool output |
| `changes.jsonl` | append-only requirement snapshots, revision chain, event hashes, and checkpoints | edited or deleted history |

Update `requirements.md` whenever the user changes the objective, acceptance standard, route, scope, constraint, or an important detail. Append the change event before acting on it, including the new current requirement snapshot, source, impact, and a concise summary. When a detail change has no full snapshot, merge it into `Current Details`; never create a revision that leaves the current requirements unchanged. Keep `task.md` limited to execution sequencing, update `findings.md` and `decisions.md` with concise evidence, and keep `handoff.md` generated by the helper. Do not write raw prompts, full tool output, or speculative conclusions.

Treat `requirements.md` as the single current requirement state and `changes.jsonl` as its append-only revision history. Never maintain a second active route or acceptance standard in another file. A small change still gets a revision when it can affect implementation, review, tests, or user-visible behavior.

Keep `manifest.task` equal to the current `requirements.md` Objective. Reject requirement-like sections in `task.md`; its execution plan is non-authoritative and must never override the current requirements.

Reject a checkpoint when the current requirements hash has no matching recorded change. Use the internal task-switch route for a distinct new task; write a resumable handoff checkpoint before archiving an active or blocked task, and never silently reuse it with a different objective.

## Retrieve Context Deliberately

1. Load the structured brief from `requirements.md`, then `task.md`, `handoff.md`, recent `changes.jsonl`, and the consistency result.
2. Stop and reconcile before retrieval when the objective differs, a transaction is incomplete, requirements are unrecorded, or revision/hash checks fail.
3. Load only the decision or finding entries relevant to the active phase.
4. For source code, inspect the current target files, related tests, and one local example before making changes.
5. Use a fresh graph or repo map only for broad structural questions. Prefer an existing Graphify graph when one is already available; otherwise use targeted `rg` searches and source inspection.
6. Do not start RAGFlow, Mem0, Cognee, Letta, Graphify, or another memory service merely to answer a task. They are optional infrastructure, not this skill's baseline.

Enforce the requested resume character budget. Include only compact change metadata in the active prompt; keep full before/after requirement snapshots on disk and in explicit historical retrieval.

Use bounded recovery tiers: current ledger first, verified project indexes second, and explicit relevant history last. Return `FOUND`, `PARTIAL`, `NOT_FOUND`, `CONFLICTED`, or `BLOCKED_UNCERTAINTY` with searched scope, budget, blocking state, and next action. Use `LIKELY_LOST` only after an explicit audit proves the authoritative record is unavailable; an empty search is only `NOT_FOUND`. Never recursively launch another recovery agent or broaden retrieval after its fixed stop point.

Before repeating research, check compact Research Receipts in `findings.md`. Reuse a current receipt with the same question and scope, locally recheck an expired receipt, and stop automatic selection on a conflicted receipt. Keep only receipt metadata and source references; do not copy full research or chat history into the ledger.

Use [selection.md](references/selection.md) when choosing an external retrieval or memory system. Use [failure-modes.md](references/failure-modes.md) when continuity has already failed or context quality is degrading.

## Optional Plan Navigation

When the project has an active, exclusive root `PLANS.md` with route coordinates, read [plan-navigation.md](references/plan-navigation.md). Treat the coordinates as a read-only position label, never as plan authority or a ledger replacement.

- Restore a coordinate only after validating the plan envelope, its single `in_progress` task, route ID, milestone mapping, and any continuity-parent return action.
- Report malformed or conflicting navigation metadata, but never inject its coordinate into a resume, MCP result, or Obsidian projection as trusted context.
- Leave projects without navigation metadata unchanged. Do not invent coordinates from conversation, ledger text, code structure, or recent activity.
- Keep `current_task_id` and `on_complete` as the machine execution semantics. Never put an `R#:A#/B#/C#` coordinate in `on_complete`.

## Obsidian Projection

Use [obsidian.md](references/obsidian.md) when the configured Obsidian Vault exists and the task has verified information worth keeping beyond the active project. Keep the project-local ledger authoritative; project notes in Obsidian are projections, not replacements. Refuse to sync a ledger with any consistency warning. Project projections must include task ID, revision, canonical requirements hash, generated-page content hashes, change log, and consistency result; archive an older task projection before replacing it. Never inject the whole Vault into the prompt.

Default Vault retrieval to current, verified, content-hash-valid notes. Exclude `历史/`, requirements snapshots, `superseded`, `needs-review`, `observed`, inconsistent, and tampered pages unless historical or diagnostic material is explicitly needed. Prefer the canonical `requirements-current` projection and deduplicate repeated matches for the same task.

## Read-Only Context Interoperability

Use the bundled read-only Context MCP when another Codex surface or third-party workbench needs current project context. Read [context-mcp.md](references/context-mcp.md) before configuring or diagnosing this integration.

- Prefer `get_current_context` for a verified resume package, `search_context` for targeted project recall, `get_context_health` for ledger/Hook diagnostics, and `list_context_projects` for configured scope discovery.
- Select these tools automatically from the task state; do not require the user to know or invoke their names.
- Require an exact project-root allowlist and a checkpoint-clean ledger. Refuse stale, tampered, cross-project, or uncheckpointed data.
- Keep historical retrieval explicit and bounded. Return revision/checkpoint metadata and summaries, not whole historical requirement snapshots by default.
- On empty, partial, conflicted, or high-risk missing results, return the recovery status, searched scope, consumed budget, blocking flag, and next action. Never fabricate a historical consensus from fragments.
- Treat MCP output as a read-only view of the project-local ledger. Route every semantic write, requirement change, checkpoint, and task switch back through the Skill-controlled lifecycle.
- Do not add an MCP write tool, background daemon, SQLite index, or multi-writer broker without measured evidence that the narrower design is insufficient.

## Composition Contract

This Skill is independently usable and remains the only authority for the project continuity ledger. Optional integrations consume a bounded envelope with `request_id`, `status`, `scope`, `evidence_refs`, `next_action`, `budget`, and baseline hashes; they never receive raw prompt history or ledger internals by default.

- `bootstrap-codex-project` owns project-file structure and plan/requirements ownership. This Skill verifies continuity and reports drift; it does not rewrite project plans.
- `intent-alignment` may provide a goal summary for a new turn. Treat it as an input to requirement-change detection, never as a replacement for `requirements.md` or a user decision.
- `diagnose`, `architecture-health`, and `tdd-loop` may add evidence references. Accept only verified, bounded references and keep their conclusions outside the ledger until the normal lifecycle records them.
- `human-centered-reasoning-guard` may require a task card, fact gate, or rebaseline. Honor that boundary; lifecycle recovery does not grant permission to bypass it.
- `deliberate-project` may provide read-only finding IDs. Preserve `Open`, `Contested`, and `Coverage-limited` states instead of converting them into decisions.

If an integration is unavailable, return the normal standalone recovery status (`FOUND`, `PARTIAL`, `NOT_FOUND`, `CONFLICTED`, or `BLOCKED_UNCERTAINTY`) with its bounded next action. Do not launch a replacement memory service or recursive recovery agent.

## Verify And Close

Use the automatic finish route before handing off or declaring a long task complete. Include verification evidence and any remaining risk in the final checkpoint. A valid ledger proves only that recovery metadata is structurally complete; it does not prove the implementation is correct.

## Guardrails

- Never auto-inject the whole ledger on every turn. Use the compact resume brief and targeted reads to stay within the attention budget.
- Treat a compaction summary as lossy evidence, never as the only memory. Reconstruct the active state from `requirements.md`, recent `changes.jsonl`, the latest handoff, and current repository state.
- Capture user-requested route, acceptance, scope, and implementation-detail changes before acting; do not wait for a final checkpoint.
- If current requirements and an older decision disagree, prefer the current revision and mark the older decision superseded rather than keeping both active.
- Do not continue while the consistency check reports unresolved conflicts.
- When a transaction marker remains after interruption, run the internal recovery route to restore its pre-transaction backups before any resume or switch.
- Do not tell the user to run `init`, `checkpoint`, `resume`, or `verify`; these are internal lifecycle operations.
- Do not ask the user to invoke `$durable-context` for ordinary complex work. Keep explicit invocation only as a fallback when the user is debugging the skill itself.
- Maintain the ledger silently. Mention it only when it materially affects a handoff, a blocker, or a recovery decision.
- Never store passwords, API keys, private prompts, raw customer data, or full untrusted documents in the ledger.
- Mark unknowns and hypotheses explicitly. Promote them to findings only after verification.
- Do not use semantic retrieval as authority. Verify retrieved memories against current code, tests, source documents, and user direction.
- Do not let background services or concurrent agents mutate the same ledger. Use separate ledgers for independent tasks and merge only verified summaries.
- Do not conclude a task is complete because a context summary says so. Re-run the relevant validation.
- Do not represent the read-only MCP as a memory authority or synchronization service. It exports only currently verified ledger state.
