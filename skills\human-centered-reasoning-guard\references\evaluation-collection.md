# Redacted Evaluation Collection

Use `scripts/collect-evaluation-candidates.ps1` to turn local conversation metadata and user-side failure reports into a review queue for guard evaluation. It reads the current session list, archived rollouts, and local rollouts. Backups are excluded by default because they are duplicate, lower-priority copies; include them only when the primary sources are incomplete.

The collector processes source text in memory only. It writes no original message text, attachment name, absolute source path, prompt, tool input, credential, cookie, token, or transcript. Each candidate contains a hashed thread identifier, source kind, observed timestamp, classifier categories, hit count, and a review status. The classifier is evidence discovery, not a verdict: every candidate remains `candidate` until a human or a later verified replay confirms the outcome.

Use the corpus to assemble matched baseline/guarded evaluation cases. Do not use a candidate as an automatic global memory rule, do not expose it as a conversation list, and do not create a new task database from it.

Run `scripts/build-evaluation-cases.ps1` after collection to create a bounded review queue. It reads only the redacted `candidates.jsonl` output, deduplicates by `case_id`, groups candidates by conservative failure-dimension hints, and writes `review-queue.jsonl`, `case-build-report.json`, and `evaluation-input-template.json` beside the collection output. The dimensions are hints for review, not observed outcomes: `false_completion`, `goal_drift`, `repeat_repairs`, and `unauthorized_actions` are discovery hints; `user_path_passed` always remains unknown until a fresh authorized replay or manual evidence review.

The generated template is intentionally not scoreable. A reviewer must fill both `baseline` and `guarded` with the same case IDs and verified metrics before invoking `scripts/score-evaluation.ps1`. This keeps keyword matches, archived duplicates, and session-index-only records from becoming false training examples or global memory rules.

Run `scripts/adjudicate-evaluation-cases.ps1` to adjudicate the collected candidates against the role/order evidence in the three local sources. The output is still redacted and contains only signal counts, source kinds, hashed case IDs, and one of these states: `confirmed_failure`, `confirmed_success`, `inconclusive_replay_required`, or `inconclusive_source_only`. A confirmed historical failure is evidence for the baseline side only; it is not proof that the guard fixes the case. The guarded side requires a fresh replay with the same case ID and acceptance path.

After collection, grouping, adjudication, and replay-manifest generation, run `scripts/validate-evaluation-artifacts.ps1`. It rejects missing files, raw-text flags, credential-like values, duplicate IDs, schema mismatches, and any candidate-set divergence across the four artifacts.
