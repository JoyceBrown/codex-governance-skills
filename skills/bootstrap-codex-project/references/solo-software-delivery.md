# Solo software delivery lifecycle

Use this module to translate a software idea or milestone into evidence-based delivery gates that one person or a very small team can sustain. Apply it only when product validation, first-release scope, reuse research, stage readiness, release preparation, or post-release direction is part of the request. Do not impose it on an isolated implementation task.

## Contents

1. Operating model
2. Lifecycle gates
3. Reuse-first research
4. Review decision
5. Project-type adjustments
6. Artifact ownership
7. Authority boundaries

## Operating model

Keep responsibility explicit:

- Let the human own target-user choice, value judgment, product priority, sensitive-data policy, irreversible decisions, and production approval.
- Let Codex organize evidence, inspect the repository, compare options, implement bounded work, run checks, and maintain the affected canonical documents.
- Treat real user observation, repository evidence, official documentation, successful probes, tests, and production signals as evidence. Do not treat model confidence or a plausible narrative as validation.
- Prefer the smallest complete value loop over a broad feature inventory.
- Reuse project capabilities and mature supported solutions before custom implementation, while accounting for dependency, license, privacy, cost, and lock-in risk.
- Advance a stage only when its blocking questions have evidence or an explicitly accepted assumption.

Do not require every gate to create a document. Route durable conclusions to existing canonical owners and keep temporary analysis in the current response.

## Lifecycle gates

### 0. Constraints and risk

Establish only constraints that can change scope, architecture, safety, or delivery:

- available developer time and maintenance capacity
- budget, operating-cost ceiling, and target release window
- target platform, deployment shape, and expected first-user scale
- personal, financial, medical, minor-related, regulated, or production data
- capabilities that must not fail and actions that require human approval

Pass when the target user, intended outcome, material constraints, and unacceptable failures are clear enough to bound the first release. Keep unresolved but reversible details `Open` or `Assumed`.

### 1. Problem evidence

Distinguish a real problem from an attractive implementation idea. Record:

- target user and concrete situation
- current alternative or workaround
- observed frequency, consequence, or friction
- available interviews, observations, usage data, or other evidence
- willingness to try, pay, or change behavior when that matters
- unverified assumptions and a lower-cost validation method

Do not let internet research or model reasoning impersonate user validation. Pass when the problem, user, current alternative, and next evidence gap are explicit. For an internal tool, repeated observed workflow friction may be sufficient evidence.

### 2. First-release value loop

Express one end-to-end loop:

```text
user trigger -> key action -> system processing -> visible result -> user benefit
```

Classify requested capabilities as:

- **Must have**: the loop fails without it.
- **Should have**: materially improves the loop but can be deferred.
- **Later**: plausible but not needed to test current value.
- **Explicitly out**: excluded to prevent accidental expansion.

Write observable acceptance outcomes, including important failure and boundary behavior. Pass when the smallest release can deliver and verify the promised result without relying on deferred features.

### 3. Technical reconnaissance

Inspect before selecting technology. Follow the reuse sequence in the next section and validate changing facts from current official sources. Separate a proposal from an adopted decision.

Pass when the recommended approach has repository and version evidence, rejected alternatives have concrete reasons, critical unknowns have a minimal probe, and long-term maintenance fits the stated constraints.

### 4. Simplest architecture and first vertical slice

Design only for the confirmed value loop and realistic near-term scale. Define:

- client, service, data, permission, and external-service boundaries
- the shortest production-shaped path from input through validation and persistence to a visible result
- error, timeout, retry, idempotency, logging, and rollback behavior that the slice actually needs
- tests and delivery evidence for the slice
- future abstractions and services deliberately omitted

For workflow, transaction, or administrative systems, clarify core entities, invariants, and state transitions before formal UI implementation. For novel interaction or visual products, use a disposable prototype when experience risk dominates, but do not silently turn it into the production architecture.

Pass when one vertical slice can expose architecture, data, integration, deployment, and user-experience risks without scaffolding the entire product.

### 5. Bounded delivery loop

For each authorized increment:

1. Read the applicable facts, decisions, code, and tests.
2. Confirm the objective, allowed scope, exclusions, acceptance outcomes, and validation.
3. Search for existing project capability before adding code or dependencies.
4. Probe uncertain APIs or environment behavior before broad integration.
5. Implement the smallest coherent increment.
6. Run proportionate static checks, tests, builds, and user-visible acceptance.
7. Review failures, permissions, data integrity, compatibility, complexity, and regression risk.
8. Update only affected canonical facts and report unverified items.

Use the current prompt for ordinary short work. Enable planning authority only for multi-stage, risky, competing, or cross-session execution. A bounded delivery loop does not itself authorize commits, pushes, deployments, migrations, purchases, or production changes.

### 6. Release readiness

Stabilize before adding more scope. Select checks proportionate to actual risk:

- core value loop and important failure paths
- lint, type checks, unit, integration, end-to-end, and production build where applicable
- authentication, authorization, data isolation, input handling, secrets, and sensitive logging
- migrations, backup, restore, rollback, and forward-fix strategy
- environment configuration, health checks, logs, metrics, alerts, and external-service failure
- dependency vulnerabilities, licenses, privacy obligations, and operating cost
- post-release smoke test and feedback channel

Return `ready`, `conditionally ready`, or `not ready`. Name blockers, evidence, release conditions, rollback triggers, and the human approval still required. Never perform the release solely because the review passes.

### 7. Feedback decision

After real use, distinguish:

- implementation failure: the intended behavior is broken
- product failure: the result does not solve a valuable problem
- operational failure: cost, reliability, support, or maintenance is unsustainable

Recommend `continue`, `fix`, `simplify`, `pivot`, or `stop`, with evidence and the next cheapest test. Do not convert every request or complaint into a feature.

## Reuse-first research

Evaluate options in this order:

1. Capability already present in the project.
2. Standard library, official SDK, CLI, integration, or maintained official example.
3. Mature maintained open-source library.
4. Reliable hosted API or service.
5. Design evidence from a mature open-source project.
6. Custom implementation.

Compare only dimensions that affect the decision, usually:

- requirement fit and target-version compatibility
- maintenance activity and documentation quality
- license, security, privacy, and data-transfer implications
- direct and transitive dependencies, binary or bundle impact
- integration effort, operating cost, and failure behavior
- vendor lock-in, adapter boundary, replacement difficulty, and removal cost

Use a minimal probe for uncertain critical behavior. Prefer custom implementation only for differentiated product value, unacceptable external cost or privacy, a genuinely tiny implementation, or a verified gap in mature options. Record the reason and a reassessment condition.

## Review decision

Assess a milestone from three perspectives without pretending they are independent agents:

| Perspective | Core question | Typical blocker |
| --- | --- | --- |
| Product | Does this deliver a verified user outcome in the first-release scope? | No target user, value loop, evidence, or observable acceptance |
| Engineering | Is the implementation evidence-based, minimal, testable, secure, and reversible? | Unverified API, avoidable custom infrastructure, unsafe data or permission boundary |
| Operations | Can the actual maintainer release, observe, recover, afford, and support it? | No rollback, backup, failure visibility, cost boundary, or support path |

For each perspective return `pass`, `conditional pass`, or `reject`, followed by blockers, evidence, and release conditions. Preserve disagreement when different risks point to different decisions.

## Project-type adjustments

| Project type | Strengthen | Common simplification |
| --- | --- | --- |
| Internal tool | Data validation, backup, one complete workflow | Fewer product documents and lighter market evidence |
| Commercial SaaS | Tenant isolation, auth, billing, privacy, observability, export and deletion | None of these because the team is small |
| Desktop app | OS compatibility, signing, updates, local data paths, offline and uninstall behavior | Hosted operations when the product is local-only |
| Mobile app | Platform permissions, background limits, weak networks, store review, third-party SDK disclosure | Server components that the first release does not need |
| AI product | Evaluation set, uncertainty, prompt injection, data leakage, cost, latency, rate limits, provider boundary | Model orchestration that has no measured value |

## Artifact ownership

- Put problem evidence, value loop, first-release scope, non-goals, success signals, and reassessment conditions in `docs/product.md` when they exceed the README.
- Put module boundaries, data flow, external adapters, and adopted technology choices in `docs/architecture.md`.
- Put entity meaning, invariants, states, and sensitive fields in `docs/data-model.md` when non-trivial.
- Put durable reuse decisions and rejected alternatives in `docs/decisions/`; create a dedicated research file only when substantial comparison must be maintained independently.
- Put test layers, important failure paths, commands, and release quality gates in `docs/testing.md`.
- Put deployment, configuration, observability, backup, recovery, rollback, operating cost, and post-release checks in `docs/operations.md`.
- Put repository-wide Codex rules and verified commands in `AGENTS.md`, not product narrative.
- Keep ordinary task details in the current prompt. Use `PLANS.md` only when planning authority is justified; do not create `TASK.md` as a second execution authority by default.

## Authority boundaries

- Ask for human approval before irreversible architecture, sensitive-data policy, authentication or authorization changes, production migration, deletion, release, purchase, or material recurring-cost decisions.
- Treat research and readiness decisions as recommendations, not side-effect authority.
- Do not initialize Git, commit, push, publish, deploy, install dependencies, or modify production solely because this lifecycle is active.
- Do not require all lifecycle gates for a routine bug fix or isolated implementation request.
- Do not create empty documents to show that a gate was considered.
