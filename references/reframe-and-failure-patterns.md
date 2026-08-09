# Reframe and Failure Patterns

## User-Outcome Questions

Translate a technical request into a real-world result:

- What is the user trying to finish, not merely what component are they naming?
- What visible state would convince a non-technical user that it works?
- What did the current behavior make them do repeatedly?
- What must remain unchanged?
- What is explicitly out of scope?

Do not treat a feature list as the definition of success. A fast, understandable, recoverable workflow is often the actual requirement.

## Common Cognitive Traps

| Trap | Observable signal | Countermeasure |
|---|---|---|
| Symptom fixation | Patching the screen where the error appears | Trace data and state backward to the originating boundary |
| Historical anchoring | Reusing an old plan or provider because it was already built | Re-state the goal and compare with a from-scratch design |
| Patch accumulation | Several unrelated edits after each failed attempt | Revert the hypothesis path conceptually; isolate one variable |
| Test substitution | Declaring success from unit tests while the user path fails | Reproduce the user's exact path on the real target environment |
| Source-of-truth collapse | Treating internal logs or full execution threads as the UI model | Separate source, execution state, presentation model, and cache |
| Completion theater | Saying "done" because a process, endpoint, or build is alive | Require fresh evidence matching the claim |
| Sunk-cost continuation | "One more fix" after repeated failure | Enter reset tier and question architecture |
| Permission blindness | Treating a vague "okay" as approval for deletion or publishing | Record exact scope, target, and rollback before mutating |
| Context contamination | Mixing projects, providers, child agents, or stale handoffs | Use explicit identity and scope fields in the task card |
| False personalization | Treating one correction or silence as a permanent preference | Store candidate experience with confidence and scope |
| Tool bias | Choosing a familiar tool rather than the tool that proves the claim | Select the cheapest reliable observation first |
| Process inflation | Adding checklists, agents, or logs without reducing risk | Apply a complexity budget and remove low-value steps |

## Three-Lens Review

### Human/Product lens

Check effort, waiting, confusion, reversibility, privacy, accessibility, and what happens on both success and failure. Ask whether the user can verify the result without knowing the implementation.

### AI reasoning lens

Check stale assumptions, premature solutions, confirmation bias, tool dependence, hidden uncertainty, path dependence, and whether the current plan merely explains its own earlier decisions.

### Engineering/governance lens

Check ownership of state, concurrency, identity, authorization, cache invalidation, observability, rollback, version drift, real-device behavior, and whether the change creates a second source of truth.

## Counterfactual Test

Before a high-risk change, answer:

1. If the current code did not exist, would this still be the chosen architecture?
2. If the user had no technical knowledge, could they complete the workflow?
3. If the network, process, or client restarted now, what state would be lost?
4. If the proposed fix is wrong, what is the safest way to discover that?

If these answers are unknown, gather evidence before writing.
