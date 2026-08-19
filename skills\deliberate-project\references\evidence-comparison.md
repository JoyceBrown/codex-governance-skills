# Evidence Comparison

Use this module when judgments depend on external sources, professional standards, conflicting evidence, causal or predictive claims, comparisons, reproduction, or measurement.

## Contents

- [Evidence record](#evidence-record)
- [Quality dimensions](#quality-dimensions)
- [Lineage and independence](#lineage-and-independence)
- [Conflict comparison](#conflict-comparison)
- [Verification and measurement](#verification-and-measurement)
- [Stopping rules](#stopping-rules)

## Evidence Record

For each material item, preserve:

```text
source_id
issuer_or_origin
exact_locator
revision_or_date
fingerprint_or_snapshot
observed_fact
applicability
direction: supports | contradicts | qualifies | contextual
lineage
observation_or_reasoning
```

Do not store raw private material in the record. Use redacted summaries and stable local locators.

## Quality Dimensions

Grade dimensions independently:

- **Authority:** ability of the source to establish this type of fact or requirement.
- **Coverage:** portion of the relevant project, population, conditions, or standard addressed.
- **Depth:** whether the source exposes mechanisms, methods, data, and limitations rather than conclusions alone.
- **Freshness:** compatibility with current project, product, jurisdiction, and standard versions.
- **Applicability:** fit to the exact claim, scope, environment, and decision.
- **Independence:** separation from other evidence lineages, instruments, assumptions, and model interpretations.
- **Traceability:** ability to retrieve and verify the exact observed content.

Use source trust states:

- `Trusted`: canonical origin, exact locator, revision/date, applicability, and provenance were retrieved and checked.
- `Qualified`: useful but authority, applicability, coverage, or provenance is partial.
- `Unverified`: retrieval or lineage cannot be confirmed.
- `Rejected`: fabricated or corrupted, irretrievable at the claimed locator, outside the stated scope, produced by a method invalid for the claimed use, or lacking intact provenance for that use.

Source trust does not automatically determine sufficiency. A trusted standard may not prove project implementation; a qualified project observation may directly reveal current behavior.

Never lower source trust merely because another applicable item is stronger or points in the opposite direction. Keep the weaker item as `Weighted`, `Compatible`, `Unresolved`, or historical context according to the conflict procedure. Use `Superseded` rather than `Rejected` for an intact older revision that remains valid in its historical scope.

## Lineage and Independence

Group reposts, derivative articles, benchmark summaries, generated answers, and copied interpretations by their upstream origin. Ten pages based on one report remain one lineage.

Check for shared:

- upstream source or dataset;
- author or vendor incentive;
- model-generated interpretation;
- unverified premise;
- measurement instrument;
- code path or test fixture;
- environment or sampling bias;
- tool failure.

Role separation does not create source independence. For consequential causal, predictive, feasibility, security, reliability, or recommendation judgments, seek a different lineage, instrument, reproduction path, or direct real-world observation when practical.

## Conflict Comparison

When evidence conflicts:

1. Confirm that both items address the same claim, version, scope, population, environment, and time period.
2. Separate contradiction from different boundary conditions or definitions.
3. Compare authority, directness, applicability, freshness, coverage, depth, and method quality.
4. Identify incentives, missing data, alternative explanations, and common-cause risk.
5. State which evidence would discriminate the interpretations.
6. Preserve unresolved conflict instead of averaging incompatible results.

Classify the result as:

- `Compatible`: different findings apply under different stated conditions.
- `Weighted`: one item is stronger for the calibrated judgment, while the weaker item remains relevant context.
- `Unresolved`: current evidence cannot distinguish the interpretations.
- `Superseded`: a newer or stronger version replaces the old scope while history remains traceable.

## Verification and Measurement

Match the instrument to the judgment:

- present behavior: direct inspection or reproducible observation;
- derived fact: repeat the transformation from source data;
- causal mechanism: discriminate material alternatives;
- prediction: ranges, sensitivity factors, indicators, and calibration against outcomes or reference classes;
- feasibility: representative path, prerequisites, validation, rollback, and cost;
- performance/reliability: representative workload/environment, baseline, threshold, variance, and confounders;
- UI/human factors: rendered workflow, representative task, accessibility/usability measure, and stated target intent;
- standard/compliance: current primary source, applicability mapping, and implementation evidence.

Do not run state-changing checks on live projects. Use an isolated copy for stateful diagnostics. Record failed and inconclusive checks; they remain evidence about coverage, not proof of the underlying claim.

## Stopping Rules

Stop evidence work when:

- the calibrated judgment has all required dimensions;
- plausible contrary evidence cannot change its stated scope;
- a discriminating check resolved the important conflict;
- remaining evidence has low expected information value;
- safety, access, or budget prevents further work and the gap is explicit.

Never search without a claim, angle, method, or coverage gap that explains why another source could matter.
