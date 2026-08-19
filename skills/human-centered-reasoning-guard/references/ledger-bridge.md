# Durable Ledger Bridge

Use `scripts/sync-durable-ledger.ps1` after a plan reconciliation, drift report, or completion receipt has been verified. The bridge does not create another task database. It converts only the redacted decision/status/receipt ID into a checkpoint through the existing `durable-context` lifecycle helper.

The bridge first validates the existing ledger. It writes one checkpoint only when explicitly invoked by the skill workflow. A level 2 or 3 drift, or a `clarify` reconciliation, becomes a `blocked` checkpoint. A valid completion receipt plus its matching passed counterfactual review becomes a `complete` checkpoint only if the durable ledger's own acceptance checks also permit completion. If the ledger rejects the checkpoint, do not bypass it by editing ledger files directly.
