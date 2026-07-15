# Joint survival uncertainty contract

The canonical artifacts are `heor/joint-survival-uncertainty.json` and `heor/joint-survival-draws.jsonl`. They carry already-generated joint survival draws into the deterministic AI4HEOR PSM engine. They are not a fitting API, approval record, or proof that a source model is valid.

## Identity and bindings

The manifest uses schema `0.1.0`, a stable `survival_uncertainty_id`, the current `analysis_id` and `psm_id`, and status `ready_for_human_review`. It binds exact bytes for:

- `heor/analysis-plan.json`;
- `heor/partitioned-survival-plan.json`;
- `heor/survival-curve-materializations.json`;
- `heor/joint-survival-draws.jsonl`;
- every local fitting, posterior, patient-level bootstrap, or transformation artifact used to generate the rows.

All paths are safe workspace-relative paths under `heor/`; all hashes are lowercase SHA-256. A changed source, base artifact, manifest, or draw file invalidates downstream approval bindings.

## Draw semantics

`draw_file.format` is `ai4heor-joint-survival-draws-jsonl@0.1.0`. Every non-empty line is exactly:

```json
{"draw_index":1,"curves":[[1.0,0.7,0.5],[1.0,0.8,0.65]]}
```

The example has only two curves for readability. A real row includes every strategy in analysis `strategy_order`, with PFS then OS for each strategy. `draw_index` starts at 1 and is sequential. The row is the sampling unit; arrays on different lines are never mixed.

`curve_order` contains exact logical paths `partitioned_survival.strategies.<strategy_id>.<endpoint>`. `time_grid_years` equals `index * cycle_length_years` from zero through `cycles`. Every curve covers that entire grid, starts at 1 within numerical tolerance, remains finite and inside `[0,1]`, and is non-increasing. At every time point, PFS is no greater than OS. The contract rejects rather than repairs invalid rows.

The row count is 1,000–10,000 and exactly equals uncertainty-plan PSA iterations. The implementation bounds the artifact at 5,000,000 values, 128 MB total, and 2 MB per line so local audit and execution remain predictable.

## Generation contract

Allowed methods are `joint_posterior` and `paired_patient_bootstrap`. `sampling_unit` is exactly `joint_draw_across_all_curves`, `independent_endpoint_sampling` is false, and `dependence_scope` is exactly `within_strategy_pfs_os` plus `between_strategy_curves`.

For a joint posterior, preserve the same posterior iteration across all coefficients and all endpoint/strategy curve evaluations. For a paired-patient bootstrap, resample the declared patient-level unit once and refit every endpoint/strategy model within that same replicate. Failed fits remain visible methodological blockers; do not replace, reorder, or filter replicates merely to meet the requested row count.

The manifest records source artifacts and a rationale, but AI4HEOR does not inspect backend-specific MCMC diagnostics, fitting code, censoring assumptions, bootstrap unit selection, treatment switching adjustments, or covariate models. Those require Human review and independent validation.

## Integration with uncertainty schema 0.12.0

The uncertainty plan binds this manifest and JSONL file by hash. Economic parameter targets remain restricted to exact state-cost or state-utility scalars under the same rules as schema `0.11.0`. In each PSA iteration, engine `0.13.0` samples the declared economic inputs and consumes the correspondingly indexed joint curve row. Base-case, DSA, and structural-scenario results continue to use the reviewed deterministic PSM curves.

The result classification is `joint_curve_draw_parameter_uncertainty` with scope `joint_survival_curves_and_economic_inputs`. The plan must not list represented strategy PFS/OS curves as omitted. It must list these unresolved structural omissions with rationale:

- `partitioned_survival.structural.curve_family_selection`;
- `partitioned_survival.structural.extrapolation_assumptions`;
- `partitioned_survival.structural.treatment_effect_duration`.

Conditional CEAC, CEAF, and per-person EVPI cover the represented joint rows and economic inputs under the selected structural assumptions. They are not complete structural uncertainty, population EVPI, EVPPI, or a reimbursement recommendation.

## Method basis

- [NICE PMG36, economic evaluation](https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2/) requires probabilistic analysis to reflect parameter correlations and requires structural uncertainty and extrapolation assumptions to be explored transparently rather than hidden by model structure.
- [NICE DSU TSD 14, survival analysis for economic evaluations](https://www.ncbi.nlm.nih.gov/books/n/nicetechsup14/pdf/) describes variance-covariance propagation for parameter uncertainty and treats alternative survival models and treatment-effect assumptions as structural scenarios.
- [NICE DSU TSD 19, partitioned survival analysis](https://sheffield.ac.uk/media/34205/download?attachment=) identifies independently modelled PFS and OS as a structural assumption and warns that independent endpoint simulation can produce incoherent PFS/OS relationships.
- [hesim partitioned-survival vignette](https://hesim-dev.github.io/hesim/articles/psm.html) demonstrates PSA by evaluating sampled parameter sets or joint posterior distributions rather than independently mixing endpoint margins.
- [Bayesian partitioned survival model](https://pmc.ncbi.nlm.nih.gov/articles/PMC8488644/) illustrates how joint posterior sampling can preserve dependence that is difficult to represent through separate marginal curves.

AI4HEOR adopts only the bounded interchange and audit contract above. It does not claim to implement every method described by these sources.
