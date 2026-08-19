# Inquiry Angles and Methods

Use this catalog to compose a bounded inquiry portfolio. Select methods because they can reveal materially different information, not because more labels appear more thorough.

## Contents

- [Prompt and requirement focus extraction](#prompt-and-requirement-focus-extraction)
- [Case continuity and comparison](#case-continuity-and-comparison)
- [Selection procedure](#selection-procedure)
- [Lightweight sentinel screen](#lightweight-sentinel-screen)
- [Observation angles](#observation-angles)
- [Reasoning methods](#reasoning-methods)
- [Conditional specialist methods](#conditional-specialist-methods)
- [Method card contract](#method-card-contract)
- [Overlap and stopping rules](#overlap-and-stopping-rules)

## Prompt and Requirement Focus Extraction

Build a focus profile before choosing angles or methods. Interpret the request as a whole; do not route from a keyword dictionary.

Extract these signal families:

| Signal | Examples | Routing effect |
| --- | --- | --- |
| Desired outcome | make money, reduce cost, ship, migrate, improve sound quality | Defines the primary success function |
| Project/domain object | music workstation, payment service, medical device | Selects domain constraints and evidence modalities |
| Actors | professional composers, buyers, operators, risk bearers | Selects observation angles and affected outcomes |
| Acceptance evidence | profit within six months, conversion, latency, crash rate | Creates testable judgment areas and measurements |
| Hard constraint | budget cap, deadline, must support VST3, must not export data | Filters options and raises feasibility checks |
| Emphasis or exclusion | focus on retention, especially recovery, do not discuss funding | Raises or suppresses inquiry budget |
| Risk and horizon | prototype, regulated launch, reversible trial, five-year operation | Changes consequence, depth, and lifecycle coverage |
| Requested output | discover details, compare, recommend, decide | Controls discovery breadth and whether adjudication runs |

Apply this precedence: governing safety, law, rights, and authorization; explicit user requirements and exclusions; acceptance evidence and stated priorities; semantic intent and emphasis; domain-critical feasibility; project evidence; repeated wording and generic keywords; generic best practice. Treat frequency as a weak clue. Never let a repeated word override an explicit exclusion, hard constraint, or the meaning of the full request.

Keep prompt-derived intent separate from project-derived facts. Use evidence to test the user's premises, not to rewrite the user's objective silently. Add an unrequested dimension only when it is a necessary condition for the requested outcome or a high-consequence governing constraint; label the reason and its budget.

Classify each explicit exclusion as:

- `Respected`: it can be omitted without invalidating the requested outcome or violating a governing constraint;
- `Conflicts-with-outcome`: honoring it removes evidence or work required to assess the requested outcome; preserve the conflict and use conditional analysis;
- `Overridden-by-governing-constraint`: applicable law, mandatory safety/right boundaries, or authorization limits require coverage despite the exclusion.

Do not use an ordinary engineering dependency, preferred practice, or generic risk to override an exclusion silently.

Preserve compound focuses and create bridge judgments instead of choosing one label:

- "Review this money-making project; focus on profitability within six months and do not discuss fundraising" routes first to revenue mechanism, costs, cash timing, demand evidence, and sensitivity; it suppresses fundraising analysis unless a governing dependency makes the exclusion impossible.
- "Review this music-production application for professional composers, especially low latency and plug-in compatibility" routes to real workflows, audio measurement, interface compatibility, failure recovery, and relevant platform or plug-in standards.
- "Review a profitable music application" creates coupled areas for monetization, willingness to pay, creative-workflow value, latency and compatibility feasibility, retention, and the causal bridges between product quality and commercial outcome.

When ambiguity between materially different focus profiles remains after inspecting available evidence, ask one consolidated question. Otherwise preserve the alternatives as labeled scenario branches and continue.

## Case Continuity and Comparison

Classify two independent axes before choosing methods:

```text
continuity_mode: Initial | Re-review
comparison_mode: Current-state | Delta
```

`Initial` means no prior inquiry record governs the current case. `Re-review` means prior finding or judgment IDs, dispositions, or verification results must be reconciled. `Current-state` inspects one declared snapshot. `Delta` compares a named baseline and current snapshot. Do not force these into one enumeration: `Re-review + Delta` is a normal combination.

In `Re-review`, reserve method capacity to retest prior material findings, but do not reveal their conclusions to an isolated role unless that role's assigned method requires historical comparison. Separate technical change from stakeholder response.

In `Delta`, add a bounded change-impact method when propagation could matter:

1. Map additions, removals, and changed controls, validation, constraints, compatibility paths, and interfaces.
2. Inspect enough unchanged context to identify governing invariants and baseline assumptions.
3. Trace affected callers, dependencies, data, states, users, operators, lifecycle stages, and recovery paths.
4. Classify whether the change resolves, preserves, amplifies, reintroduces, or supersedes a prior condition.
5. Scale depth by consequence and impact radius: deep for governing or high-consequence paths, focused for bounded dependencies, and local only when propagation is demonstrably contained.

Do not treat a diff as complete evidence of the resulting system. Do not run change-impact work for a current-state case without a real baseline.

## Selection Procedure

For each priority judgment area:

1. Derive the area from the focus profile, case profile, coverage ledger, sentinel results, domain-critical conditions, prior material findings when applicable, and project evidence; record which signal justified its priority.
2. Classify the judgment as factual, causal, predictive, feasibility, normative, comparative, preference, or recommendation.
3. Identify consequence, uncertainty, reversibility, affected actors, lifecycle stages, system boundaries, and evidence modalities.
4. Select the smallest set of angles and methods likely to produce distinct findings.
5. Assign every selected method to a baseline role or supplementary probe.
6. Record its evidence requirement, output, budget, stopping condition, and known limitation.
7. Mark a material dimension without a usable method as `Coverage-limited`.

Prefer one method from several distinct families over several near-duplicates from one family. Do not run the whole catalog.

## Lightweight Sentinel Screen

Run one bounded sentinel screen after the breadth map and before specialist routing. This is a trigger check, not eight full reviews. Record `Positive`, `Negative-with-evidence`, `Unknown`, or `Not-applicable` for each domain:

```text
security_privacy_and_authorization
reliability_and_recovery
human_factors_accessibility_and_misuse
data_quality_models_and_measurement
dependencies_supply_chain_and_provenance
governance_legal_licensing_and_economics
capacity_cost_and_resources
lifecycle_migration_compatibility_and_external_effects
```

Base a negative result on inspected project evidence, not missing keywords. Treat hidden data flow, generic component names, indirect downloads, external effects, model-backed scoring, generated artifacts, and absent accessibility or recovery documentation as possible quiet triggers. Route `Positive` and high-consequence `Unknown` results to the closest applicable specialist method or a supplementary domain probe. If no viable method or modality exists, create a coverage gap. Do not run every specialist method merely to clear the screen, and do not treat a completed sentinel as professional domain assurance.

## Observation Angles

Angles determine where to look. Combine them with reasoning methods.

| Angle | Primary question | Typical trigger |
| --- | --- | --- |
| End user | What changes in the user's actual task and outcome? | User-facing behavior or adoption risk |
| Operator/support | Can people detect, operate, recover, and support it? | Production or support workflow |
| Developer/maintainer | What becomes harder to understand, test, evolve, or own? | Architecture or long-lived code |
| Decision owner | Who can authorize goals, tradeoffs, exceptions, and residual risk? | Recommendation or governance conflict |
| Affected non-owner | Who bears cost or harm without decision authority? | Cross-team or rights impact |
| Component | What is locally true inside one module? | Local design or implementation fact |
| Interface | What assumptions, states, and failures cross a boundary? | Multi-component or multi-project system |
| Whole system | What emerges from interactions and feedback? | Coupling, scale, or cascading effects |
| Before/during/after | What differs before transition, during it, and after steady state? | Migration, rollout, or incident |
| Lifecycle | What changes across design, build, deploy, operate, upgrade, and retire? | Long-term consequence |
| Normal/degraded/recovery | How does behavior change outside the happy path? | Reliability or safety risk |
| Small/current/large scale | Which assumptions fail under different load or scope? | Growth or performance claim |
| Current/future environment | What depends on versions, regulation, vendors, or organization? | Evolution and obsolescence risk |

## Reasoning Methods

### First-Principles Decomposition

Reduce the design to necessary goals, constraints, mechanisms, and resources. Use when convention, inherited architecture, or vague requirements may be driving the solution. Output unnecessary assumptions and the minimum conditions for success.

### Assumption Audit

List explicit and implicit premises, their owners, evidence, sensitivity, and failure indicators. Use for uncertain environments, inferred user behavior, external dependencies, or predictions. Do not treat every unknown as equally material.

### Causal and Mechanism Tracing

Trace how an input or decision produces the claimed outcome, including alternative causes and observable indicators. Use for root-cause, performance, reliability, adoption, or policy-effect claims. Correlation alone is insufficient.

### Counterfactual Analysis

Change one material premise, intervention, or environmental condition and determine which judgments survive. Use to expose fragile recommendations and distinguish causes from accompanying conditions.

### Reverse Reasoning

Start from the required outcome, acceptance condition, or imagined failure and work backward to necessary states and controls. Use for incomplete implementation paths, incident preparation, and missing acceptance criteria.

### Alternative-Path Analysis

Generate materially different options, including status quo and deferral, then identify prerequisites and disqualifying constraints. Use when the current solution may reflect path dependence. Cosmetic variants do not count as alternatives.

### Comparative and Reference-Class Analysis

Compare with version-matched reference implementations, mature practice, failed cases, or a relevant outside-view class. State comparability limits. Use for architecture, cost, schedule, reliability, and industry-practice judgments.

### Scenario and Branch Analysis

Define actor, stimulus, environment, expected response, measurable bound, and recovery for a small set of high-consequence scenarios. Use for architecture qualities, staged rollout, abnormal conditions, and variable user contexts. Cap scenarios by consequence and uncertainty.

### System-Relationship Analysis

Map dependencies, state transitions, feedback loops, ownership boundaries, propagation paths, and shared resources. Use for cross-component or multi-project scope. Separate direct dependency from inferred influence.

### Lifecycle and Evolution Analysis

Trace consequences through creation, migration, operation, upgrade, compatibility, deprecation, and retirement. Use when a locally attractive choice may shift cost or risk into the future.

### Stakeholder and Distribution Analysis

Map outcomes, burdens, authority, incentives, and recourse for materially affected groups. Use when benefits and harms are uneven. Do not invent preferences for absent stakeholders.

### Constraint-Conflict Analysis

Separate mandatory boundaries, binding commitments, engineering facts, authorized objectives, recommended practice, and preferences. Use when requirements cannot all be satisfied. Report the authority or renegotiation needed rather than inventing a compromise.

### Sensitivity Analysis

Vary uncertain inputs, preference weights, thresholds, or environmental assumptions and identify when a judgment changes. Use for recommendations, forecasts, costs, and capacity decisions. Use ranges or ordinal comparisons when precise numbers lack evidence.

### Value-of-Information Analysis

Ask whether obtaining another item of evidence could change the decision enough to justify its cost, delay, or risk. Use when verification is expensive. Do not use unsupported numerical precision.

### Traceability Analysis

Trace requirements to design, implementation, configuration, tests, runtime evidence, and user outcome. Use for inconsistency audits and change impact. Missing traceability is a gap, not proof of missing behavior.

## Conditional Specialist Methods

### Threat, Abuse, and Privacy-Flow Analysis

Trigger on sensitive data, trust-boundary changes, untrusted input, privileged actions, external exposure, or autonomous side effects. Require assets/data, actors and capabilities, flows/retention, abuse paths, controls, residual risk, and verification targets.

### Hazard and Failure Analysis

Trigger on high consequence, irreversible action, regulated or physical behavior, tightly coupled components, or common-mode risk. Select a domain-appropriate technique such as failure-mode analysis, fault trees, or control-loop analysis. Require hazards, causal scenarios, controls, detection, recovery, and residual-risk ownership.

### Human-Factors and Work-as-Done Analysis

Trigger on human-in-the-loop control, UI, accessibility, training, support burden, vulnerable users, or high error consequence. Require representative tasks and environments, observed or rendered workflow, likely errors, recovery, workload, accessibility, and direct user/operational evidence when available.

### Operational-Resilience Review

Trigger on deployment, migration, stateful change, external dependencies, service objectives, scale, or incident responsibility. Require service objectives, dependency failure behavior, capacity, telemetry, alertability, rollout, rollback, recovery targets, runbooks, ownership, and rehearsal evidence.

### Economic and Resource Analysis

Trigger when cost, staffing, infrastructure, licensing, opportunity cost, or maintenance burden could change feasibility or priority. Separate one-time, recurring, switching, failure, and option-preservation costs. Do not infer business priorities.

### Governance and Accountability Analysis

Trigger on recommendations, conflicting stakeholders, contracts, waivers, cross-team ownership, or uncertain authority. Distinguish decision, approval, execution, operation, and residual-risk acceptance. Unknown authority remains user-dependent; inquiry does not assign authority.

### Measurement, Experiment, and Independent Reproduction

Trigger when a consequential claim could be discriminated empirically. Predeclare hypothesis, baseline, metric, threshold, representative environment/sample, confounders, protocol, uncertainty, and stopping rule. Use a different instrument or lineage when checking common-cause risk.

## Method Card Contract

For each selected method, record only:

```text
method
priority_area
trigger
owner
angles
required_evidence
expected_output
budget
budget_scope: cumulative-case
stopping_condition
limitations
```

Do not create a second evidence ledger. Reference the shared evidence and finding IDs.

## Overlap and Stopping Rules

- Merge methods that ask the same question with the same evidence modality.
- Keep methods separate when they use a different actor, time horizon, mechanism, instrument, or source lineage.
- A specialist label without distinct evidence or operation is not a new method.
- A completed method does not prove that its angle is fully covered.
- Stop a method when its decision-relevant questions are answered, a material gap is explicit, added work is unlikely to change the judgment map, or its budget is exhausted.
- Stop the portfolio when the global information-gain conditions in `SKILL.md` are satisfied.
