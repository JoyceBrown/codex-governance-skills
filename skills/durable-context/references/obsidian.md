# Obsidian Projection

The configured Obsidian vault is an optional second layer for cross-session and cross-project memory. The project-local `.agent-context/` ledger remains authoritative for the active task.

## Default Vault

Set `DURABLE_CONTEXT_VAULT` to the Obsidian Vault path for the current machine. If it is not set, the bridge falls back to `~/Obsidian/上下文系统`.

Use `scripts/obsidian_bridge.py` as the internal bridge. It has no third-party Python dependency.

## Automatic Use

- Initialize the vault only when it is missing or structurally incomplete.
- Sync a project after a verified checkpoint or final completion, not on every turn.
- Sync only the current ledger projection: objective, status, checkpoint, handoff, decisions, and findings.
- Include the task ID, requirements revision, append-only change log, and consistency result in every generated project projection.
- Project a plan coordinate and `PLANS.md` source hash only when the optional navigation envelope passes validation. If navigation is configured but invalid, record that it was rejected without copying the coordinate or hash into trusted frontmatter.
- Keep the complete current `requirements.md` in the canonical current-requirements projection and one historical note for every available revision. The project overview links to the canonical page instead of duplicating its body.
- When a new task replaces a completed task in the same project, archive the old projection before updating the current page.
- Search the vault only when the task needs cross-project recall or the user asks for historical context. Exclude history, revision snapshots, inconsistent pages, invalid content hashes, and unverified statuses by default; enable them only for explicit historical or diagnostic retrieval.
- Write a curated long-term note only when the fact is verified or the user explicitly asks to remember it.
- Keep unverified material in `06-收件箱/` with `needs-review` status.

## Trust And Precedence

1. Current user instruction.
2. Current files, tests, official source documents, and authoritative external state.
3. Project-local `.agent-context/` ledger.
4. Obsidian project projections.
5. Curated cross-project long-term notes.

Never use an Obsidian note to override current code or an explicit user instruction. Treat stale or conflicting notes as leads that require re-verification.

The current route and acceptance standard have one active source: the project's `requirements.md`. Obsidian mirrors are never a second active requirements source. Older projections are historical and must be marked `superseded`.

An optional route coordinate remains owned by the active root `PLANS.md`. The Obsidian page is only a hash-bound read-only projection and cannot authorize execution or repair a conflicting plan.

## Internal Operations

- `init`: create the vault structure without overwriting existing notes.
- `sync`: refuse inconsistent ledgers, then update the hashed generated projection and project index.
- `verify`: validate structure, registry, unique current roots and task IDs, task/revision/hash agreement, generated-page body hashes, canonical current requirements, and archive markers.
- `search`: perform bounded, deduplicated text retrieval with source, consistency, and content-hash metadata. The default route is fail-closed unless the current project root is supplied and its local ledger passes freshness validation; results are restricted to the current task and a total character budget.
- `remember`: write one scoped note with a source and status; default to `needs-review` unless verification is explicit.

Generated pages are marked `managed_by: durable-context`. Human-curated notes should live in the decision, finding, long-term, or inbox directories and must not be silently overwritten.
