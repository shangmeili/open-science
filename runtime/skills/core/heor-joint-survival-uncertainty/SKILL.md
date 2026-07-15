---
name: heor-joint-survival-uncertainty
description: Create, repair, or audit hash-bound joint PFS and OS curve draws for an AI4HEOR partitioned-survival PSA. Use when a reviewed joint posterior or paired-patient bootstrap must propagate its declared dependence through heor/joint-survival-uncertainty.json and heor/joint-survival-draws.jsonl, including an explicit between-strategy assumption; do not use for independent endpoint sampling, curve fitting, curve-family selection, or approval.
---

# HEOR Joint Survival Uncertainty

Create a backend-neutral survival-draw artifact that one deterministic AI4HEOR PSA can consume row by row. Read [references/contract.md](references/contract.md) before creating or changing either artifact.

## Workflow

1. Read the exact current bytes of `heor/analysis-plan.json`, `heor/partitioned-survival-plan.json`, `heor/survival-curve-materializations.json`, and `heor/treatment-effect-duration.json`. Use `$heor-partitioned-survival` and `$heor-treatment-effect-duration` first when deterministic curves or duration scenarios are not coherent and review-bound.
2. Confirm current analysis schema `0.15.0`, PSM schema `0.7.0`, treatment-duration schema `0.1.0`, states exactly `progression_free`, `progressed`, `dead`, and one common analysis time grid. Create joint manifest `0.4.0`; prior current manifest `0.3.0` remains readable. Legacy analysis `0.12.0` / PSM `0.3.0` or `0.4.0` with manifest `0.1.0` or `0.2.0` also remains readable.
3. Confirm there is already either a reviewed joint posterior or a complete `$heor-paired-survival-bootstrap` result that covers every strategy PFS and OS endpoint. This Skill audits and packages those draws; it does not fit survival models or reconstruct covariance from marginal intervals.
4. Reject independent PFS/OS sampling. One draw row is the transport unit across all curves. A joint posterior must declare a source distribution that represents within- and between-strategy dependence. A stratified bootstrap of independent parallel arms preserves within-strategy PFS/OS dependence but must declare conditional independence between strategies; never upgrade that assumption into observed correlation.
5. Copy [assets/joint-survival-uncertainty.template.json](assets/joint-survival-uncertainty.template.json) to `heor/joint-survival-uncertainty.json`. Bind the exact analysis, PSM, source materialization, treatment-duration, draw-file, and source-artifact bytes by lowercase SHA-256.
6. Write `heor/joint-survival-draws.jsonl` using [assets/joint-survival-draws.example.jsonl](assets/joint-survival-draws.example.jsonl) only as a shape example. Each line contains exactly a sequential `draw_index` and a `curves` array following manifest `curve_order`; never copy the example values into a real analysis.
7. Use curve order `strategy_order`, then `pfs`, `os` within each strategy. Each curve has exactly `cycles + 1` finite survival values on the declared time grid, starts at 1, stays in `[0,1]`, and never increases. For every strategy and time point, require PFS no greater than OS.
8. Use 1,000–10,000 rows, exactly equal to `probabilistic_analysis.iterations` in `heor/uncertainty-plan.json`. Keep the total at or below 5,000,000 survival values, the JSONL file at or below 128 MB, and every line at or below 2 MB.
9. State generation method, strategy resampling design, between-strategy assumption, represented dependence scope, source bindings, rationale, and limitations. Every draw must represent the selected base duration scenario using the same declared endpoint policies; alternative duration scenarios remain separate deterministic structural results. Preserve curve-family selection and extrapolation assumptions as explicit omissions. Do not list treatment-effect duration as omitted when the current PSM binds it.
10. Set status to `ready_for_human_review` only after all files and hashes are final, then run:

```bash
python3 runtime/skills/core/heor-joint-survival-uncertainty/scripts/validate_joint_survival_uncertainty.py \
  heor/analysis-plan.json heor/partitioned-survival-plan.json \
  heor/survival-curve-materializations.json heor/uncertainty-plan.json \
  heor/joint-survival-uncertainty.json heor/joint-survival-draws.jsonl \
  --treatment-effect-duration heor/treatment-effect-duration.json \
  --workspace-root .
```

11. Use `$heor-uncertainty-analysis` schema `0.14.0` to combine each joint curve row with recalculated cost, utility, and event components, or legacy schema `0.12.0` with its economic reward-vector inputs. The deterministic base case, DSA, and structural scenarios keep the reviewed base curves.

## Boundaries

- Do not generate independent marginal endpoint draws and label them joint.
- Do not infer a joint distribution from confidence intervals, reconstruct covariance, pair unrelated posterior rows, repair crossing curves, clamp values, filter failed rows, or silently reduce the draw count.
- Do not claim between-strategy correlation from separately randomized parallel arms merely because their independently resampled rows share a replicate number.
- Do not claim the validator establishes statistical fit, clinical plausibility, external validity, correct extrapolation, convergence of a source MCMC, or appropriateness of a bootstrap.
- Do not use the artifact to choose curve families, select a duration scenario, average models, or claim that one base-duration PSA resolves structural alternatives.
- Do not create approval events, accept assumptions, or claim independent validation. The Human reviews the method and evidence; an independent implementation remains a release gate.
- Do not call conditional CEAC, CEAF, or EVPI a reimbursement recommendation, complete uncertainty, population EVPI, or research-priority result.

## Handoff

Report the two artifact paths and hashes, generation method, source artifact paths and hashes, curve order, time-grid size, draw count, validator result, represented dependence scope, structural omissions, and exact Human or independent-validation blocker. Keep calculation reproducibility distinct from methodological validity.
