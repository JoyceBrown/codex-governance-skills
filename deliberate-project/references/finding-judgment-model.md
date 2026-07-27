# Finding and Judgment Model

Use this module to normalize discoveries, cross-expand them, preserve disagreement, and synthesize a traceable judgment landscape.

## Contents

- [Keep output types separate](#keep-output-types-separate)
- [Finding card](#finding-card)
- [Judgment card](#judgment-card)
- [Relationships](#relationships)
- [Relation record](#relation-record)
- [Cross-expansion](#cross-expansion)
- [Discovery states](#discovery-states)

## Keep Output Types Separate

- **Observation:** content directly seen in a source or reproducible project state.
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

## Finding Card

Use a stable ID and keep the card concise:

```text
finding_id
statement
role
angle
method
priority_area
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

Cross-expansion seeks additional information rather than matching language. For every material first-round finding, peers may:

- add independent evidence;
- expose a counterexample or boundary;
- add an actor, lifecycle stage, interface, consequence, or opportunity;
- connect it to another finding or shared premise;
- split an overbroad finding into condition-specific items;
- provide a competing explanation;
- propose a discriminating check;
- confirm that no material addition was found within the assigned method.

Require representation attestation from the originating role: every material first-round item is mapped, explicitly excluded with a reason, or marked lost due to coverage/runtime failure. This checks preservation, not correctness or completeness.

## Discovery States

- `Observed`: directly observed in applicable project evidence or a reproducible check.
- `Supported`: evidence currently supports the calibrated judgment.
- `Contested`: material contrary evidence or interpretation remains.
- `Conditional`: valid only under visible conditions.
- `Open`: evidence cannot currently distinguish important possibilities.
- `User-dependent`: requires an authorized preference, priority, or governance decision.
- `Coverage-limited`: a role, angle, method, evidence dimension, or inspection modality is missing.
- `Superseded`: a newer version replaces the item while history remains.

States may coexist across dimensions. A judgment can be supported but coverage-limited, or conditional and contested. Do not collapse evidence basis, sufficiency, project implementation state, and safety assurance into one label.

Store states as a set in `current_states`; never overwrite one valid state with another. Keep `uncertainty` explicit and describe its source, direction or range when known, sensitivity, and what could reduce it. Use `Snapshot-stale` as a temporary processing state when drift invalidates the observation boundary; do not synthesize it until the affected work is rebound or rerun.

Inquiry completion is evaluated by coverage and expected information gain, not by making all judgment states match.
