# Performance And Cost Budget

Keep the guard proportional to the task. These are budgets for the bundled scripts, measured on the local workstation; a slower machine may report a warning rather than a correctness failure.

| Path | Budget | Required behavior |
|---|---:|---|
| Light workflow routing | 2 seconds | Return a decision without reading a transcript or memory store. |
| Candidate metadata grouping | 10 seconds | Process redacted `candidates.jsonl` only. |
| Local adjudication | 180 seconds per 1.5 GB | Stream files; never load a whole rollout into memory or write raw text. |
| Memory retrieval | 2 seconds for 10,000 records | Return at most 20 records and filter project scope before ranking. |
| Regression/adversarial tests | 120 seconds | Synthetic fixtures only; no network or production process. |

If a budget is exceeded, record the measured cost and reduce the input scope or add an incremental snapshot. Do not skip identity, authorization, drift, or user-path checks to make the timing pass.
