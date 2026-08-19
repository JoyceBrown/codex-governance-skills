# Adaptive Task Tiering

Use `scripts/classify-task-tier.ps1` before a multi-step task or when choosing whether to create a task card. The classifier prevents two opposite failures: treating a high-impact task as a casual edit, and turning a simple question into a long process.

| Tier | Trigger | Minimum behavior |
|---|---|---|
| `light` | Read-only question or one low-risk local change | State the real goal, visible result, authorization, and one check |
| `full` | Cross-boundary change, debugging, deployment, external state, interruption, or risky action | Use task card, fact/goal gates, plan reconciliation, drift check, and real-path verification |
| `reset` | Same symptom failed twice, user says unchanged, or evidence conflicts | Stop the current patch path; collect a discriminating observation before any new write |

The classifier is evidence about process depth, not proof that a requested action is correct. Current authorization and verified facts still control what may happen next.
