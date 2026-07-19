# Synthetic cost-effectiveness teaching example

This example is an AI4HEOR onboarding asset for a researcher-led, auditable
cost-utility workflow. It compares a hypothetical intervention with a
hypothetical comparator in a three-state cohort model:

`stable -> progressed -> dead`

All values in `inputs/model-inputs.csv` are synthetic proposed assumptions.
They are not clinical evidence, unit-cost evidence, a jurisdictional reference
case, or a reimbursement recommendation.

The example is intentionally small enough to hand-check. Its calculation does
not depend on a model provider or third-party Python package. The versioned
`run_analysis.py` reads the hash-bound CSV and `analysis-spec.json`, validates
the complete transition, cost, and utility structure, uses Decimal arithmetic,
and writes a deterministic JSON result with cycle traces.

Verify the unmodified teaching case without writing an output file:

```bash
python run_analysis.py --check expected/base-case-result.json
```

Create the base-case result:

```bash
python run_analysis.py --output outputs/base-case-result.json
```

Run the declared low one-way sensitivity scenario without editing the source
inputs:

```bash
python run_analysis.py --intervention-stable-cost 14400 \
  --output outputs/intervention-stable-cost-low.json
```

A useful Human-led workflow is:

1. confirm or revise the decision problem and intended use;
2. review the state structure, cycle timing, transition rows, costs, utilities,
   discounting, and time horizon;
3. verify the expected result, then calculate discounted costs, QALYs, and
   incremental results with the bundled deterministic code;
4. vary one explicitly selected input through the declared command-line option;
5. write a report that distinguishes numerical results from scientific and
   policy judgments.

The expected result proves only that the exact teaching calculation is
reproducible. The Human researcher remains responsible for every methodological
choice and interpretation. AI4HEOR may prepare and audit artifacts but cannot
approve this model or treat the synthetic inputs as evidence.
