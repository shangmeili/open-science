# Synthetic cost-effectiveness teaching example

This example is an AI4HEOR onboarding asset for a researcher-led, auditable
cost-utility workflow. It compares a hypothetical intervention with a
hypothetical comparator in a three-state cohort model:

`stable -> progressed -> dead`

All values in `inputs/model-inputs.csv` are synthetic proposed assumptions.
They are not clinical evidence, unit-cost evidence, a jurisdictional reference
case, or a reimbursement recommendation.

The example is intentionally small enough to hand-check. A useful workflow is:

1. confirm or revise the decision problem and intended use;
2. review the state structure, cycle timing, transition rows, costs, utilities,
   discounting, and time horizon;
3. calculate discounted costs, QALYs, and incremental results with deterministic
   code;
4. vary one explicitly selected input in a transparent sensitivity check;
5. write a report that distinguishes numerical results from scientific and
   policy judgments.

The Human researcher remains responsible for every methodological choice and
interpretation. AI4HEOR may prepare and audit artifacts but cannot approve this
model or treat the synthetic inputs as evidence.
