# Hook Integration Boundary

Use the host lifecycle Hook only for mechanical enforcement. In this environment, the installed `durable-context` Hook already validates project ledgers on `UserPromptSubmit`, intercepts write-capable `PreToolUse` calls when a requirement revision is pending, and checks recovery on `Stop`.

Do not register a competing global `PreToolUse` deny hook from this skill. Two independent deny policies can block their own recovery writes or make a simple task appear stuck. Instead, use the durable ledger as the project continuity layer and run this skill's fact, goal, reconciliation, drift, and completion checks as the semantic layer.

If a future integration needs host enforcement, compose it through one audited dispatcher with these rules:

1. Preserve read-only work and recovery commands.
2. Deny only a specific unsafe call, never the whole workbench or turn.
3. Return the smallest evidence-gathering or reconciliation action that can unblock progress.
4. Do not read or persist raw prompts, tool arguments, transcripts, credentials, or product content.
5. Keep hook output short and do not claim a task is complete from Hook state alone.

Consult the official Codex Hooks documentation before changing a global hook configuration. Hook trust is hash-based and a changed command hook must be reviewed before it runs.
