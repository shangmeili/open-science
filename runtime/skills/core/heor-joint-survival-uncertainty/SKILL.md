---
name: heor-joint-survival-uncertainty
description: Create, repair, or audit hash-bound joint PFS and OS curve draws for an AI4HEOR partitioned-survival PSA. Use when a reviewed joint posterior or paired-patient bootstrap must propagate dependence within each strategy's PFS/OS endpoints and between strategy curves through heor/joint-survival-uncertainty.json and heor/joint-survival-draws.jsonl; do not use for independent endpoint sampling, curve fitting, curve-family selection, or approval.
---

# HEOR Joint Survival Uncertainty

Create a backend-neutral survival-draw artifact that one deterministic AI4HEOR PSA can consume row by row. Read [references/contract.md](references/contract.md) before creating or changing either artifact.

## Workflow

1. Read the exact current bytes of `heor/analysis-plan.json`, `heor/partitioned-survival-plan.json`, and `heor/survival-curve-materializations.json`. Use `$heor-partitioned-survival` first when any deterministic curve is not already coherent and review-bound.
2. Confirm analysis schema `0.12.0`, PSM schema `0.3.0`, states exactly `progression_free`, `progressed`, `dead`, and one common analysis time grid. Stop on any mismatch.
3. Confirm there is already either a reviewed joint posterior or a paired-patient bootstrap output that jointly covers every strategy PFS and OS endpoint. This Skill audits and packages those draws; it does not fit survival models or reconstruct covariance from marginal intervals.
4. Reject independent PFS/OS sampling. One draw row must be the sampling unit across all curves and preserve both within-strategy PFS/OS dependence and between-strategy curve dependence.
5. Copy [assets/joint-survival-uncertainty.template.json](assets/joint-survival-uncertainty.template.json) to `heor/joint-survival-uncertainty.json`. Bind the exact analysis, PSM, deterministic materialization, draw-file, and source-artifact bytes by lowercase SHA-256.
6. Write `heor/joint-survival-draws.jsonl` using [assets/joint-survival-draws.example.jsonl](assets/joint-survival-draws.example.jsonl) only as a shape example. Each line contains exactly a sequential `draw_index` and a `curves` array following manifest `curve_order`; never copy the example values into a real analysis.
7. Use curve order `strategy_order`, then `pfs`, `os` within each strategy. Each curve has exactly `cycles + 1` finite survival values on the declared time grid, starts at 1, stays in `[0,1]`, and never increases. For every strategy and time point, require PFS no greater than OS.
8. Use 1,000–10,000 rows, exactly equal to `probabilistic_analysis.iterations` in `heor/uncertainty-plan.json`. Keep the total at or below 5,000,000 survival values, the JSONL file at or below 128 MB, and every line at or below 2 MB.
9. State generation method, source bindings, rationale, and limitations. Preserve curve-family selection, extrapolation assumptions, and treatment-effect duration as explicit structural omissions in uncertainty schema `0.12.0`; the joint draw artifact does not resolve them automatically.
10. Set status to `ready_for_human_review` only after all files and hashes are final, then run:

```bash
python3 runtime/skills/core/heor-joint-survival-uncertainty/scripts/validate_joint_survival_uncertainty.py \
  heor/analysis-plan.json heor/partitioned-survival-plan.json \
  heor/survival-curve-materializations.json heor/uncertainty-plan.json \
  heor/joint-survival-uncertainty.json heor/joint-survival-draws.jsonl \
  --workspace-root .
```

11. Use `$heor-uncertainty-analysis` to execute schema `0.12.0`. The deterministic base case, DSA, and structural scenarios keep the reviewed base curves; each PSA iteration consumes exactly one joint curve row plus its declared economic-input draws.

## Boundaries

- Do not generate independent marginal endpoint draws and label them joint.
- Do not infer a joint distribution from confidence intervals, reconstruct covariance, pair unrelated posterior rows, repair crossing curves, clamp values, filter failed rows, or silently reduce the draw count.
- Do not claim the validator establishes statistical fit, clinical plausibility, external validity, correct extrapolation, convergence of a source MCMC, or appropriateness of a bootstrap.
- Do not use the artifact for curve-family selection, time-varying treatment-effect selection, treatment-effect waning, model averaging, or structural extrapolation scenarios.
- Do not create approval events, accept assumptions, or claim independent validation. The Human reviews the method and evidence; an independent implementation remains a release gate.
- Do not call conditional CEAC, CEAF, or EVPI a reimbursement recommendation, complete uncertainty, population EVPI, or research-priority result.

## Handoff

Report the two artifact paths and hashes, generation method, source artifact paths and hashes, curve order, time-grid size, draw count, validator result, represented dependence scope, structural omissions, and exact Human or independent-validation blocker. Keep calculation reproducibility distinct from methodological validity.
