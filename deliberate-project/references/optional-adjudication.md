# Optional Adjudication

Read this module only when the user explicitly asks to choose, recommend, prioritize, approve, reject, or make a final project decision. Discovery remains complete and reportable without this stage.

## Contents

- [Entry gate](#entry-gate)
- [Decision procedure](#decision-procedure)
- [Constraint order](#constraint-order)
- [Decision states](#decision-states)
- [Stopping and reporting](#stopping-and-reporting)

## Entry Gate

Require:

- an explicit decision request;
- a defined decision owner or a visible authority gap;
- a stable option set or a reason options remain incomplete;
- material findings and competing judgments already reported;
- criteria that come from authorized intent rather than agent invention.

If these are absent, report the judgment landscape and the smallest missing user decision or evidence item.

## Decision Procedure

1. Define the decision, owner, horizon, and status quo.
2. List materially feasible options and explicit exclusions.
3. Apply hard constraints before preferences.
4. Map each surviving option to outcomes, risks, opportunities, prerequisites, reversibility, switching cost, and residual uncertainty.
5. Expose the tradeoff rule and any authorized weights or risk tolerance.
6. Run sensitivity analysis when plausible changes could reverse the recommendation.
7. Use value-of-information analysis when another check could change the choice enough to justify its cost or delay.
8. Preserve minority findings and contrary evidence in the decision record.

Do not average incompatible criteria or assign numerical weights without evidence. An ordinal comparison is preferable to false precision.

## Constraint Order

1. Applicable law, mandatory standards, fundamental rights, explicit authorized prohibitions, and mandatory safety/security/privacy controls establish hard boundaries within their verified scope.
2. Binding contracts, interoperability commitments, and approved decisions constrain options within their real scope.
3. Engineering and operational facts determine feasibility.
4. Authorized objectives select among compliant and feasible options.
5. Recommended practice improves lifecycle and risk outcomes.
6. Team and tool preferences apply last.

If constraints conflict or eliminate every option, report the waiver, renegotiation, authority, or evidence needed to reopen the option space.

Do not convert every nonzero safety, security, or privacy risk into an absolute prohibition. Separate mandatory controls from recommended controls and residual risk. Apply an authorized risk threshold and identify who may accept the residual risk; if either is unknown, use `User decision required` rather than inventing a zero-risk rule or declaring `No feasible option`.

## Decision States

- `Recommended`: one option remains preferable across the stated criteria and plausible ranges.
- `Recommended with conditions`: the option depends on visible prerequisites, limits, or verification.
- `Multiple viable options`: the evidence supports more than one option and the remaining choice is a legitimate preference or strategy decision.
- `User decision required`: authority, priority, risk tolerance, or tradeoff weights are missing.
- `Evidence insufficient`: a material uncertainty prevents a responsible choice.
- `No feasible option`: current hard constraints exclude all considered paths.

Role agreement is not a decision state and role count is not a weighting mechanism.

## Stopping and Reporting

Stop when one decision state is justified, the smallest missing decision/evidence is isolated, or the budget is exhausted. Report:

- selected state and exact scope;
- option comparison and tradeoff rule;
- binding constraints and authority;
- sensitivity and residual uncertainty;
- conditions, rollback/reconsideration triggers, and consequences;
- material contrary findings that remain relevant.

Adjudication does not authorize implementation or external side effects.
