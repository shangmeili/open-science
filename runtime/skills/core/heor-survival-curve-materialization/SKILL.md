---
name: heor-survival-curve-materialization
description: Materialize and validate AI4HEOR exponential-rate or Weibull AFT shape/scale survival curves from Human-selected, hash-bound fit outputs. Use when reviewed PFS, OS, or other absolute survival endpoints must be evaluated on an analysis cycle grid; when partitioned-survival inputs must be numerically reproduced from selected model parameters; or when fit-output, review, evaluator, grid, and curve-value provenance must fail closed before approval.
---

# HEOR Survival Curve Materialization

Create `heor/survival-curve-materializations.json` so every admitted survival value is reproduced from one typed selected fit output. Read [references/contract.md](references/contract.md) before editing artifacts.

## Workflow

1. Read the exact analysis plan, partitioned-survival plan, and every referenced schema `0.2.0` survival review.
2. Confirm a Human has selected a converged `exponential` or `weibull` candidate for each required absolute curve. Stop for every other family or unresolved selection.
3. Convert each selected backend output into the strict local shape in [assets/typed-survival-fit-output.template.json](assets/typed-survival-fit-output.template.json). Preserve the backend artifact separately; do not guess or silently translate a parameterization.
4. Use only `exponential_rate` with `rate_per_year`, or `weibull_shape_scale_aft` with `shape` and `scale_years`. Require positive finite parameters and years.
5. Copy [assets/survival-curve-materializations.template.json](assets/survival-curve-materializations.template.json). List curves in analysis strategy order, with PFS then OS for each strategy.
6. Bind the exact analysis, review, and typed fit-output bytes. Set basis IDs to the exact review hash, fit-output hash, and evaluator identity required by the contract.
7. Evaluate every boundary from time zero through `cycles * cycle_length_years`. Do not interpolate, smooth, splice, clamp, round, or repair values.
8. Copy the exact materialized time, survival, and basis IDs into the partitioned-survival plan. Bind the materialization manifest hash from that plan.
9. Run:

```bash
python3 runtime/skills/core/heor-survival-curve-materialization/scripts/validate_survival_curve_materializations.py \
  heor/analysis-plan.json heor/partitioned-survival-plan.json \
  heor/survival-curve-materializations.json --workspace-root .
```

10. Leave status `draft` and report exact blockers until all hashes, parameters, targets, values, and reviews pass. `ready_for_human_review` is not approval.

## Boundaries

- Keep natural-language rationale primary; use structured rows only for exact inputs and review.
- Do not fit data, reconstruct IPD, select a family, infer covariance, apply treatment effects, or claim clinical or external validity.
- Do not accept Weibull PH rate/shape, `survreg` coefficients, transformed optimizer coefficients, covariate models, mixtures, cure models, splines, generalized families, competing risks, or non-year units.
- Do not claim evidence verification, Human approval, independent validation, cost effectiveness, reimbursement, or policy authority.

## Deliverable

Return the manifest path, typed fit-output paths, exact hashes, validator result, unsupported curves, and next Human gate. Keep approval outside the Skill output.
