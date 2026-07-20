---
name: heor-survival-curve-materialization
description: Materialize and validate AI4HEOR standard parametric survival curves from Human-selected, hash-bound survHE outputs. Use when reviewed PFS, OS, or another absolute survival endpoint must be evaluated on an analysis cycle grid; when partitioned-survival inputs must be numerically reproduced from exponential, Weibull, Gompertz, gamma, generalized gamma, generalized F, lognormal, or loglogistic parameters; or when fit-output, review, evaluator, grid, and curve-value provenance must fail closed before approval.
---

# HEOR Survival Curve Materialization

Create `heor/survival-curve-materializations.json` so every admitted survival value is reproduced from one typed selected fit output. Read [references/contract.md](references/contract.md) before editing artifacts.

## Workflow

1. Read the exact analysis plan, partitioned-survival plan, and every referenced survival review. Use materialization schema `0.2.0` only with a first-party review schema `0.3.0`; retain materialization `0.1.0` only for the legacy external-import path.
2. Confirm a Human has selected one converged reviewed family for every required absolute curve. The Skill reproduces that decision; it never selects a family.
3. For schema `0.2.0`, bind the selected normalized model JSON emitted by `$heor-survival-fit-execution` directly. Require its exact natural parameterization and transform names only into the explicit year-based manifest names in the contract. Do not infer coefficients or units.
4. Preserve schema `0.1.0` typed fit-output handling only for exponential and Weibull external imports. Do not convert a schema `0.3.0` first-party output into that legacy shape.
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
- Do not accept Weibull PH rate/shape, `survreg` coefficients, transformed optimizer coefficients, covariate models, mixtures, cure models, splines, competing risks, or non-year units.
- Reproduce a negative Gompertz shape exactly, but expose its non-zero limiting survival as a clinical-plausibility risk for Human review.
- Do not claim evidence verification, Human approval, independent validation, cost effectiveness, reimbursement, or policy authority.

## Deliverable

Return the manifest path, normalized fit-output paths, exact hashes, validator result, unsupported curves, and next Human gate. Keep approval outside the Skill output.
