# Complete synthetic cost-utility teaching case

This example is an AI4HEOR onboarding asset for a researcher-led, auditable,
end-to-end cost-utility workflow. It compares a hypothetical intervention with
a hypothetical comparator in a three-state cohort model:

`stable -> progressed -> dead`

All values in `inputs/model-inputs.csv` are synthetic proposed assumptions.
They are not clinical evidence, unit-cost evidence, a jurisdictional reference
case, or a reimbursement recommendation.

The case is complete as a worked teaching workflow, not as a real economic
evaluation. It includes a decision problem, conceptual model, assumptions
register, evidence-gap log, base case, eight-parameter deterministic
sensitivity analysis, three structural scenarios, a 1,000-draw fixed-seed
probabilistic teaching analysis, mechanical validation record, draft report,
and researcher review checklist. The calculation does not depend on a model
provider or third-party Python package. The versioned `run_analysis.py` reads
the hash-bound CSV and `analysis-spec.json`, validates the transition, cost,
utility, and uncertainty structures, uses Decimal arithmetic, and writes a
deterministic JSON result with cycle traces.

Verify the unmodified teaching case without writing an output file:

```bash
python run_analysis.py --check expected/base-case-result.json
```

Create the complete result and draft report:

```bash
python run_analysis.py --output outputs/complete-case-result.json \
  --report-output outputs/teaching-report.md
```

Run the declared low one-way sensitivity scenario without editing the source
inputs:

```bash
python run_analysis.py --intervention-stable-cost 14400 \
  --output outputs/stable-cost-low-result.json
```

Run the declared high scenario in the same way:

```bash
python run_analysis.py --intervention-stable-cost 21600 \
  --output outputs/stable-cost-high-result.json
```

In the AI4HEOR desktop app, selecting this teaching starter installs the full
case without starting a model turn. The explicit **Run complete case** action
verifies that the installed runner, specification, inputs, and expected result
still match the bundled bytes; runs the base case, deterministic sensitivity
analysis, structural scenarios, and fixed-seed probabilistic teaching analysis;
creates the report; and records the run and provenance locally. The run does
not require a configured model and sends no case content to a model provider.
Edited inputs are preserved, but the app refuses to describe them as the fixed
teaching calculation.

A useful Human-led workflow is:

1. review the decision problem and intended use;
2. inspect the conceptual model, assumptions register, and evidence gaps;
3. verify the expected result and calculate discounted costs, QALYs, and
   incremental results;
4. inspect eight one-way sensitivity ranges, three structural scenarios, and
   the bounded probabilistic teaching analysis;
5. distinguish automated mechanical checks from Human and independent review;
6. review the generated report and complete the researcher checklist.

The expected result proves only that the exact teaching calculation is
reproducible. The Human researcher remains responsible for every methodological
choice and interpretation. AI4HEOR may prepare and audit artifacts but cannot
approve this model or treat the synthetic inputs as evidence.
