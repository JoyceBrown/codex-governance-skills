# Recovery Status Vocabulary

This is the single semantic source for recovery states used by `durable-context`,
`project-agent-orchestrator`, and the `composition-v1` envelope. The JSON schema
stores the allowed values; it does not define their meaning.

| Status | Meaning | Required behavior |
| --- | --- | --- |
| `FOUND` | The requested evidence is present, current, and verified. | Continue only within the verified scope. |
| `PARTIAL` | Some required evidence is present, but a bounded gap remains. | Perform one targeted check, then close or stop. |
| `NOT_FOUND` | The bounded search found no matching authoritative evidence. | Stop at the recovery point; do not infer from chat memory. |
| `CONFLICTED` | Authoritative sources disagree. | Reconcile against current files and the latest user instruction before acting. |
| `BLOCKED_UNCERTAINTY` | Missing or uncertain evidence matters to a high-risk action. | Verify the authoritative external state or request a decision; do not retry automatically. |

`LIKELY_LOST` is a diagnostic conclusion only. It may be used after an explicit
audit proves that the authoritative record is unavailable; an empty search is
`NOT_FOUND`. Every recovery result should include searched scope, consumed budget,
blocking state, and one next action. Recovery stops after one targeted supplement,
one external-state check, and at most two attempts at the same repair.
