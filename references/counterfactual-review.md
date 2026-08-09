# Counterfactual Completion Review

Use `scripts/review-completion-counterfactual.ps1` after the completion receipt and before a complete checkpoint. The review asks whether the apparent success could still be false because of a wrong target, stale artifact/runtime, source divergence, refresh/restart behavior, or a rejected path that displays success.

Each required check must contain a redacted evidence reference and a `pass` result. This is a disproof attempt, not a restatement of the happy path. It does not replace the user path; it makes the user-path conclusion harder to falsify.
