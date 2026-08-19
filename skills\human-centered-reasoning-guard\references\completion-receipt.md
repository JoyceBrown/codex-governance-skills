# Completion Receipt

Completion is a claim about the user's result, not about a plan checkbox, code diff, process liveness, or one passing unit test. Before declaring a multi-step task complete, run `scripts/validate-completion-receipt.ps1` with redacted evidence for the target identity/version, authoritative source, artifact, runtime, and user path.

The receipt rejects completion unless all required states are verified, the user path passed, identity is verified, and the current drift level is zero. It produces a deterministic receipt ID from the redacted facts. Store only the receipt ID and concise evidence references in the task card or durable ledger; do not store transcripts, tokens, cookies, or raw logs.

If the receipt fails, return to investigation or verification. Do not rewrite the goal to fit the available evidence.
