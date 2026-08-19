# Goal Integrity Gate

The fact gate protects the system from unsupported mutations. The goal integrity gate protects the user from a technically valid action that solves the wrong problem.

Run `scripts/goal-integrity-gate.ps1` after the fact gate and before the causal action. The input must state the current instruction, the real-world goal, the visible success state, the proposed action, its predicted effect, the source of truth, and a falsifiable observation. For a mutation, also provide the exact target, authorization, and rollback. For completion, provide fresh evidence and the user-path result.

The gate does not prove semantic causality. It forces the agent to make its causal claim and disproof condition explicit so that a cheap observation can redirect the work. A failed gate blocks only the proposed action; the next action should be evidence collection or a new hypothesis, not an unrelated patch.
