# Active User-Perspective Reconstruction

Use this reference only when the user explicitly asks the guard to understand a requirement from the user's perspective before implementation. It is a bounded read-only mode, not a product strategy workshop and not a second project plan.

## What This Mode Solves

The user may name a feature, component, API, or implementation as shorthand for a result they want in real life. Active mode tests that shorthand against the user's actual workflow:

```text
表面请求 / named solution
        -> why now / triggering problem
        -> user job / what they are trying to finish
        -> expected experience / what should feel easy, clear, and recoverable
        -> observable result / what they can see or do when solved
        -> failure and recovery / what must not be lost or repeated
```

Do not assume that the named solution is the goal. Do not assume that a plausible underlying goal is confirmed merely because it sounds user-centered.

## Bounded Evidence

Read in this order and stop when the result is determined:

1. Current user request and any explicit constraints.
2. Latest user corrections, observed symptoms, or acceptance language in the current task.
3. The active plan, requirements, or project facts directly named by the request.
4. One authoritative user-visible observation when the request refers to an existing behavior.

Retrieve older durable context only to resolve a known continuity question. Never use a stale handoff, memory item, or old plan to override the current user instruction. Do not search the whole repository, full transcript, or global experience store unless another skill has established that it is necessary.

## Reconstruction Questions

Answer briefly, using evidence labels:

- **Surface request:** What did the user ask for, and what solution did they name?
- **Why now:** What event, friction, risk, or repeated cost caused the request?
- **User job:** What does the user need to finish, decide, avoid, or regain control over?
- **Expected experience:** What should the user be able to do, see, understand, and recover from?
- **Observable success:** What would a non-technical user accept as solved?
- **Invariants and costs:** What must remain unchanged, and what waiting, confusion, repetition, privacy, or data-loss cost matters?
- **Proxy check:** Is the named feature the goal, or only one possible route to it?
- **Alternatives:** Is there a materially simpler or more direct way to produce the same user result? Mention at most two, and do not recommend one without evidence.

Classify statements as:

```text
FACT       directly stated or freshly observed
ASSUMPTION inferred from current evidence; include confidence high/medium/low
UNKNOWN    cannot be resolved without the user or a targeted check
```

## Decision Rules

- `CONTINUE`: the requested outcome is clear, the named direction plausibly serves it, and no high-impact unknown remains. Continue only with the next bounded step, not an automatic edit.
- `REFRAME`: the named solution and the likely user job diverge, or the current plan optimizes a proxy while leaving the user-visible problem intact. Explain the break in `WHY -> WHAT -> HOW`.
- `ASK`: two plausible interpretations would change scope, architecture, authorization, privacy, or acceptance. Ask no more than three questions, and only questions whose answers change the decision.
- `STOP`: the request has no useful user-visible outcome, is already satisfied, is unauthorized, or further work would add cost without increasing certainty.

“NO CHANGE REQUIRED” is a valid `STOP` result. A passing build, healthy process, or technically elegant design is not user-outcome evidence by itself.

## Output Contract

Return this compact receipt and stop before implementation:

```text
Active user-perspective review

Surface request:
Likely user job:
Why now:
Expected experience:
Observable success:
Must remain unchanged:
Facts:
Assumptions (with confidence):
Unknowns:
Proxy or goal mismatch:
Key risk/cost:
Decision: CONTINUE | REFRAME | ASK | STOP
Next action: one bounded read-only check, one question, or explicit handoff to implementation
```

Do not include private chain-of-thought. The receipt should contain the reasoning needed for the user to correct the interpretation, not an exhaustive internal transcript.

## Handoff

Only after the user confirms or explicitly asks to proceed may the agent hand the receipt to `intent-alignment`, `diagnose`, `bootstrap-codex-project`, or implementation. The handoff envelope contains only the goal, visible success, scope, constraints, unknowns, decision, and evidence references. It does not grant authorization or create a second source of truth.
