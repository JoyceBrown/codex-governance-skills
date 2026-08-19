# Finding and Judgment Model

Use this module to normalize discoveries, cross-expand them, preserve disagreement, and synthesize a traceable judgment landscape.

## Contents

- [Keep output types separate](#keep-output-types-separate)
- [Clue card](#clue-card)
- [Finding card](#finding-card)
- [Judgment card](#judgment-card)
- [Relationships](#relationships)
- [Relation record](#relation-record)
- [Cross-expansion](#cross-expansion)
- [Synthesis and checkpoint manifests](#synthesis-and-checkpoint-manifests)
- [Re-review and response classification](#re-review-and-response-classification)
- [Discovery states](#discovery-states)

## Keep Output Types Separate

- **Observation:** content directly seen in a source or reproducible project state.
- **Clue:** a concrete observation, anomaly, negative-space signal, or unresolved relation that may become material only when combined with other information.
- **Finding:** a material detail exposed by a role-angle-method combination.
- **Judgment:** a calibrated interpretation derived from one or more findings.
- **Assumption:** a provisional premise needed to continue analysis.
- **Competing explanation:** an alternative account that fits some or all observations.
- **Risk:** a possible adverse consequence with conditions and affected boundaries.
- **Opportunity:** a possible beneficial consequence with prerequisites and tradeoffs.
- **Preference:** an explicitly authorized priority or value choice.
- **Evidence gap:** a required dimension that has not been established.
- **Verification proposal:** a safe check that could materially change the judgment landscape.

Do not recast preferences as engineering facts or observations as causal explanations.

## Clue Card

Record a clue when a specific observation may combine with another role, surface, state, boundary, or lifecycle stage even though it is not yet material. Keep the card minimal and redacted; reference private evidence by stable locator or digest rather than copying sensitive content.

```text
clue_id
exact_locator
redacted_observation
why_unusual
entity_or_boundary
missing_condition
related_clue_ids
role_method_provenance
state: Open | Connected | Promoted | Explained | Deferred
disposition_reason
```

Use `Open` until the clue-fusion pass; `Connected` when a supported relation is recorded; `Promoted` when it contributes to a material finding; `Explained` when evidence establishes a non-material explanation; and `Deferred` only with a named coverage or budget consequence. `Deferred` is unfinished: if the clue could still combine into a material item, it prevents `Complete`. Do not discard a clue solely because it is individually non-material before materiality filtering and cross-role fusion.

If clue volume exceeds the bounded context or inquiry budget, partition clues by surface and consequence, preserve their IDs and locators, and mark the unprocessed partition `Deferred`; never summarize it away as if fusion occurred.

Include negative-space clues for an expected control, test, owner, monitor, rollback path, evidence class, or artifact that was not found. Absence is a clue rather than proof until the expected existence and inspection coverage are established.

## Finding Card

Use a stable ID and keep the card concise:

```text
finding_id
statement
role
angle
method
priority_area
supporting_clue_ids
evidence_ids
basis: Direct | Derived | Inferred | Assumed
scope_and_conditions
project_impact
affected_actors
novelty: new | corroborates | contradicts | extends | reframes
verification_if_material
coverage_limit
```

A finding is material when it changes a judgment, option, risk, opportunity, professional sufficiency assessment, or a premise on which another material item depends.

Role agents leave lifecycle, stakeholder response, and response classification to the primary. After evidence comparison and cross-checking, the primary may append:

```text
technical_change_state
stakeholder_response_state
response_class
```

## Judgment Card

Create a versioned judgment only after findings are mapped:

```text
judgment_id_and_version
statement
type
scope_and_conditions
supporting_findings
contrary_findings
assumptions
competing_judgments
required_evidence_dimensions
satisfied_dimensions
missing_dimensions
consequence_if_wrong
uncertainty
affected_actors
current_states
next_discriminating_check
```

Version the judgment when wording, scope, conditions, or meaning changes. Do not change a finding's wording to manufacture compatibility; create a qualified or competing judgment instead.

## Relationships

Use explicit typed links:

- `supports`: increases support for the target under stated conditions;
- `contradicts`: provides incompatible evidence or interpretation;
- `depends_on`: the target requires the source premise;
- `causes`: proposes a mechanism, not merely sequence;
- `qualifies`: narrows scope, confidence, or conditions;
- `alternative_to`: represents a competing explanation or option;
- `supersedes`: replaces a prior version while preserving history.

Check important dependency chains. A top-level judgment cannot be stronger than a material unresolved premise it depends on.

## Relation Record

Use a stable relation record when a link is material, conditional, contested, causal, or changes who bears an outcome:

```text
relation_id_and_version
source_item_id
relation_type
target_item_id
evidence_ids
scope_and_conditions
affected_actors
role_method_provenance
current_states
```

Version the relation independently when its endpoints, type, conditions, or affected actors change. Do not hide a contested causal edge inside narrative text or treat the existence of two findings as evidence for their relationship.

## Cross-Expansion

Cross-expansion seeks additional information rather than matching language. Before materiality filtering, fuse all `Open` clues across roles by shared entity, actor, trust or system boundary, state, time/order, lifecycle stage, invariant, upstream condition, downstream consequence, or expected-but-absent control. Text similarity alone is not a relation. Record supported links, promote material combinations, and give every remaining clue an explicit disposition.

For every open clue combination and material first-round finding, peers may:

- add independent evidence;
- expose a counterexample or boundary;
- add an actor, lifecycle stage, interface, consequence, or opportunity;
- connect it to another finding or shared premise;
- split an overbroad finding into condition-specific items;
- provide a competing explanation;
- propose a discriminating check;
- confirm that no material addition was found within the assigned method.

Require representation attestation from the originating role: every submitted clue and material first-round item is mapped, explicitly dispositioned with a reason, or marked lost due to coverage/runtime failure. This checks preservation, not correctness or completeness. In sequential mode, reconcile the separate role-packet ID manifest but retain `representation_attestation=Unavailable-sequential`; the primary cannot attest on behalf of an absent originating context.

## Synthesis and Checkpoint Manifests

Maintain a synthesis manifest before presentation compression:

```text
item_id
item_type: clue | finding | judgment | contrary | minority | coverage_gap
final_disposition
related_item_ids
output_mapping
omission_reason
```

Every material item, material contrary item, minority interpretation, and decision-relevant coverage gap must map to the final structured record or carry a visible exclusion reason. A compact user answer may map several items to one paragraph, but absence from the visible summary does not remove them from the record; disclose when the answer is only a summary.

Before host compaction, handoff, or a context-limited sequential continuation, create a checkpoint manifest containing snapshot IDs, clue/finding/judgment/source IDs, counts, relation endpoints, unresolved states, unconsumed role packets, and pending verification. After restoration, reconcile every ID, count, relation endpoint, and pending state before synthesis. Recover a mismatch from the source snapshot or mark the affected coverage `Partial`; never infer that omitted state did not exist.

## Re-review and Response Classification

Keep three questions separate:

- **Technical change:** what happened to the project condition?
- **Stakeholder response:** what did an authorized person do about it?
- **Required attention:** how should the current report present it after evidence and consequence checks?

For `Re-review` or `Delta`, use `technical_change_state` only when prior or baseline evidence exists:

- `New`: not present in the governing prior record or baseline scope;
- `Persisting`: the same material condition still exists;
- `Resolved`: applicable evidence verifies that the condition no longer exists;
- `Regressed`: a previously resolved condition returned;
- `Superseded`: a newer finding or changed scope replaces the prior meaning;
- `Not-rechecked`: current access, snapshot, or method did not support a responsible retest.

Use `stakeholder_response_state` independently when a response is evidenced:

- `Unaddressed`, `Acknowledged`, `Contested`, `Deferred`, or `Accepted-risk`.

Acknowledgment does not prove resolution. No response does not prove persistence. Accepted risk does not weaken the technical finding or authorize another party to accept it.

After evidence comparison, mechanism-to-consequence tracing, counterargument testing, common-cause review, and bidirectional impact calibration, assign one `response_class`:

- `Governing-blocker`: verified applicable law, mandatory safety/security/privacy control, authorization boundary, binding constraint, or engineering infeasibility blocks the stated goal within the finding's scope;
- `Material-concern`: the finding could materially change success, risk, feasibility, cost, stakeholder outcome, or a consequential judgment and needs visible resolution or acceptance;
- `Improvement`: a supported enhancement with value that does not invalidate the stated goal or current judgment;
- `Observation`: useful context that requires no present action.

An uncertain severe possibility is not a governing blocker; keep it `Material-concern` with `Open`, `Conditional`, or `Coverage-limited` as appropriate. Response class is not evidence strength, confidence, discovery state, inquiry completion, or adjudication. Reviewer count never determines it.

## Discovery States

- `Observed`: directly observed in applicable project evidence or a reproducible check.
- `Supported`: evidence currently supports the calibrated judgment.
- `Contested`: material contrary evidence or interpretation remains.
- `Conditional`: valid only under visible conditions.
- `Open`: evidence cannot currently distinguish important possibilities.
- `User-dependent`: requires an authorized preference, priority, or governance decision.
- `Coverage-limited`: a role, angle, method, evidence dimension, or inspection modality is missing.
- `Superseded`: a newer version replaces the item while history remains.

States may coexist across dimensions. A judgment can be supported but coverage-limited, or conditional and contested. Do not collapse evidence basis, sufficiency, technical change, stakeholder response, response class, project implementation state, and safety assurance into one label.

Store states as a set in `current_states`; never overwrite one valid state with another. Keep `uncertainty` explicit and describe its source, direction or range when known, sensitivity, and what could reduce it. Use `Snapshot-stale` as a temporary processing state when drift invalidates the observation boundary; do not synthesize it until the affected work is rebound or rerun.

Inquiry completion is evaluated by coverage and expected information gain, not by making all judgment states match.
