# Hook Integration Boundary

Use the host lifecycle Hook only for narrow mechanical enforcement. The default `durable-context` template does not register `UserPromptSubmit`; a diagnostic installation may observe lexical requirement hints as privacy-safe telemetry, but it must not turn them into a write gate. `PreToolUse` permits ordinary project work and denies only direct file writes inside the authoritative `.agent-context` directory. Project, Git, plan, and generated-projection drift remain advisory. `Stop` may request one bounded continuation only for an incomplete ledger transaction, then opens a circuit instead of repeatedly interrupting the task.

Do not register a competing global `PreToolUse` deny hook from this skill. Two independent deny policies can block their own recovery writes or make a simple task appear stuck. Instead, use the durable ledger as the project continuity layer and run this skill's fact, goal, reconciliation, drift, and completion checks as the semantic layer.

If a future integration needs host enforcement, compose it through one audited dispatcher with these rules:

1. Preserve read-only work and recovery commands.
2. Deny only a specific unsafe call that threatens authority-owned state or irreversible loss, never the whole workbench or turn.
3. Return the smallest evidence-gathering or reconciliation action that can unblock progress.
4. Do not read or persist raw prompts, tool arguments, transcripts, credentials, or product content.
5. Keep hook output short and do not claim a task is complete from Hook state alone.

Consult the official Codex Hooks documentation before changing a global hook configuration. Hook trust is hash-based and a changed command hook must be reviewed before it runs.
