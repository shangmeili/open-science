---
name: heor-population-adjusted-comparison
description: Prepare, execute, audit, and explain one bounded local anchored matching-adjusted indirect comparison (MAIC) using randomized two-arm IPD for one treatment-versus-common-comparator trial and aggregate relative-effect evidence for a second treatment-versus-common-comparator trial. Use when a researcher needs population adjustment for prespecified effect-modifier imbalance, exponential-tilting mean balance, effective sample size and weight diagnostics, deterministic stratified bootstrap uncertainty, or an app-owned Human method review before considering the estimate in HEOR. Reject unanchored comparisons, single-arm evidence, disconnected evidence, STC, ML-NMR, prognostic-only matching, automatic effect-modifier selection, weight trimming, and unreviewed downstream use.
---

# HEOR Population-Adjusted Comparison

Keep the researcher in scientific control. Assist with preparation, deterministic local execution, audit, and explanation; never choose effect modifiers, the target population, the estimand, the outcome scale, or downstream model use.

## Route the method before touching data

1. Use this Skill only for the fixed anchored MAIC contract in [references/anchored-maic-contract.md](references/anchored-maic-contract.md).
2. Stop if the randomized evidence lacks a common comparator, IPD is unavailable for the two-arm IPD trial, or the target aggregate trial does not report every Human-prespecified effect-modifier mean.
3. Route STC, ML-NMR, unanchored MAIC, larger networks, survival outcomes, missing-data models, higher moments, interactions, weight trimming, or alternative calibration estimators to a separately admitted method. Do not approximate them here.

## Prepare the request through conversation

1. Start from `assets/anchored-maic-request.template.json` and write `heor/population-adjusted-comparison-request.json` only after the researcher specifies the population, treatments, common comparator, outcome/timepoint, estimand, effect scale, effect modifiers, target population, and uncertainty settings.
2. Require one strict pseudonymous CSV with `subject_id,treatment,outcome` followed by the declared numeric effect-modifier columns. Reject direct identifiers, missing values, non-randomized treatment assignment, or any treatment other than the declared IPD treatment and common comparator.
3. Bind one aggregate-evidence JSON containing the exact target means and the aggregate treatment-versus-common-comparator estimate and standard error on the same linear-predictor scale.
4. Classify patient-level data before execution. Keep all IPD and derived artifacts local; never send row content to a model or connector.
5. Explain that exact mean balance proves only the declared moments were balanced. It does not prove overlap, complete effect-modifier capture, transportability, internal validity, or absence of residual bias.

## Validate, authorize, and execute

Run from the Skill directory:

```bash
python scripts/validate_anchored_maic_request.py \
  --workspace /absolute/workspace \
  --request heor/population-adjusted-comparison-request.json
```

After the researcher authorizes the exact local command, run:

```bash
python scripts/run_anchored_maic.py \
  --workspace /absolute/workspace \
  --request heor/population-adjusted-comparison-request.json
```

The runner installs nothing, uses only the Python standard library, writes atomically, and emits no copied IPD. It refits exponential-tilting weights in every fixed PCG32 stratified bootstrap replicate. Any failed replicate is retained and blocks review eligibility.

Audit the result independently through the portable replay:

```bash
python scripts/audit_anchored_maic_result.py \
  --workspace /absolute/workspace \
  --result heor/population-adjusted-comparison-runs/<execution_id>/manifest.json
```

## Hand off to Human review

Leave a complete result at `awaiting_method_review`. The desktop, not this Skill, owns acceptance or rejection and requires all eight checks:

- question, estimand, target population, and common comparator;
- randomized connected evidence and source provenance;
- scale-specific effect-modifier rationale and completeness;
- IPD classification, missingness, and treatment/outcome integrity;
- target-moment compatibility and overlap;
- convergence, exact balance, weights, and ESS;
- bootstrap failures, precision, and aggregate-effect uncertainty;
- residual bias, transportability, limitations, and downstream suitability.

Acceptance only makes the exact result eligible for later evidence selection. It does not approve an analysis plan, select a preferred treatment, prove scientific validity, or automatically populate an economic model.
