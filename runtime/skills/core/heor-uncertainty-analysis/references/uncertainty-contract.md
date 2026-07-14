# Uncertainty-plan contract

The canonical artifact is `heor/uncertainty-plan.json`. It is an executable specification for the first-party deterministic engine, not free-form code and not an approval record.

## Links and identity

- `analysis_id` equals the current analysis plan.
- `base_analysis.path` is exactly `heor/analysis-plan.json`.
- `base_analysis.content_sha256` is the lowercase SHA-256 of the current plan bytes.
- The analysis plan contains only the fixed artifact path under `uncertainty_analysis`; the app records the uncertainty artifact hash in the app-owned analysis-plan approval event. This avoids a circular pair of file hashes.
- A changed plan or uncertainty artifact invalidates the relevant approval binding.

## Parameter contract

Each parameter contains a stable `id`, label, JSON Pointer `target`, dot-path `provenance_path`, deterministic bounds and rationale, and a probabilistic distribution with basis IDs and rationale.

Allowed parameter targets use `/strategies/<strategy_id>/...`; analysis schemas `0.8.0` through `0.11.0` IDs come from `strategy_order`, while legacy plans use comparator/intervention roles:

- scalar state costs and utilities;
- a complete static transition-matrix row;
- a complete scheduled row at `/strategies/<strategy_id>/transition_schedule/<phase>/matrix/<row>`;
- a positive `rate_per_year` for one admitted `constant_competing_rates` event, including under analysis `0.8.0` with uncertainty `0.7.0`;
- a positive exponential `rate_per_year` or Weibull `shape` or `scale_years` for one admitted survival transformation, including under analysis `0.8.0` with uncertainty `0.7.0`;
- a `source_probability` strictly inside `(0,1)` for one admitted probability-time event, including under analysis `0.8.0` with uncertainty `0.7.0`.
- only under analysis `0.9.0` with uncertainty `0.8.0`, the exact positive `excess_mortality_rate_per_year.value` of one admitted background-mortality transformation.
- only under analysis `0.10.0` with uncertainty `0.9.0`, the exact positive `relative_effect.value` of one admitted RR/OR transformation.
- only under analysis `0.11.0` with uncertainty `0.10.0`, the exact positive `hazard_ratio.value` of one admitted constant-HR transformation.

Probability-row and schedule-change targets do not apply to a schema `0.5.0` transition derived from constant competing rates. Changing only the derived output makes its deterministic transformation snapshot stale, so the engine rejects it. A rate target must use the exact JSON Pointer `/input_provenance/<mapping>/derivation/transformation/phases/<phase>/rows/<row>/events/<event>/rate_per_year`; its `provenance_path` must equal that indexed mapping's transition path, and its sole `basis_id` must equal the event's `source_extraction_id` or `assumption_id`.

For a survival parameter, the exact JSON Pointer is `/input_provenance/<mapping>/derivation/transformation/parameters/<parameter>/value`. The indexed mapping must be an admitted survival transformation in analysis schema `0.6.0` or `0.8.0`, the parameter name must match its exponential or Weibull distribution, `provenance_path` equals the complete schedule path, and the sole `basis_id` equals that parameter's `source_extraction_id` or `assumption_id`.

For a source probability, the exact JSON Pointer is `/input_provenance/<mapping>/derivation/transformation/phases/<phase>/rows/<row>/event/source_probability`. The indexed mapping must be an admitted single-event probability-time transformation in analysis schema `0.7.0` or `0.8.0`, `provenance_path` equals its complete matrix or schedule path, and the sole `basis_id` equals that event's `source_extraction_id` or `assumption_id`.

For background mortality, the exact JSON Pointer is `/input_provenance/<mapping>/derivation/transformation/excess_mortality_rate_per_year/value`. The indexed mapping must use analysis schema `0.9.0`, the exact background-plus-excess operation, and a complete two-state schedule path. Uncertainty schema `0.8.0` permits no other parameter target. Its sole `basis_id` equals the excess rate's extraction or assumption basis. The engine recomputes every cycle from `1-exp(-(-ln(1-q_annual)+h_excess)*cycle_length_years)`. Life-table metadata and annual probabilities, review bases, the operation, and all other transformation internals remain fixed. Required structural scenarios may replace only state cost or utility scalars, discount rates, or half-cycle correction; cycle count/length and transition matrices/schedules are excluded because they would invalidate the fixed transformation.

For relative effects, the exact JSON Pointer is `/input_provenance/<mapping>/derivation/transformation/relative_effect/value`. The indexed mapping must use analysis schema `0.10.0`, `relative_effect_to_transition_schedule`, and a complete two-state schedule path; uncertainty schema `0.9.0` permits no other target. The sole `basis_id` equals the relative effect's extraction or assumption basis. RR DSA high and bounded Uniform PSA high are strictly below `1/max(baseline q>0)`; unbounded RR distributions fail closed. OR permits Lognormal or strictly positive bounded Uniform PSA. Baselines, measure, intervals, review bases, operation, and all other transformation internals remain fixed.

For a hazard ratio, the exact JSON Pointer is `/input_provenance/<mapping>/derivation/transformation/hazard_ratio/value`. The indexed mapping uses analysis schema `0.11.0`, `hazard_ratio_to_transition_schedule`, and a complete two-state schedule; uncertainty schema `0.10.0` permits no other target. The sole `basis_id` equals the HR extraction or assumption basis. DSA bounds and a strictly positive bounded Uniform PSA bracket the base HR. Both high bounds must keep `-expm1(-HR * max(delta_H0))` finite and below 1. Baseline cumulative hazards, all five review bases, indices, operation, and other internals remain fixed. Unbounded HR distributions fail closed.

For each DSA run or PSA draw, engine version `0.8.0` applies every sampled parameter to an ephemeral plan copy and recomputes admitted transformations once after all replacements. Compatible legacy plans retain engine `0.7.0` output. This preserves row sums, competing-event allocation, survival or probability-time consistency, derivation integrity, and fail-closed validation. It does not admit coordinated transformation-space structural scenarios.

Supported probabilistic distributions:

- `beta(alpha, beta)` for bounded 0–1 quantities;
- `gamma(shape, scale)` or `lognormal(mu_log, sigma_log)` for positive quantities;
- `uniform(low, high)` only when the evidence supports a bounded uniform assumption;
- `dirichlet(alpha[])` for a complete probability simplex such as a transition row.

An event rate, survival-curve parameter, or uncertain background excess rate is positive but not intrinsically bounded by 1, so these targets accept only gamma, lognormal, or uniform with `low > 0`. DSA low/high values must also be positive and bracket the base. Beta and Dirichlet are rejected. A background analysis may declare a zero fixed excess rate, but uncertainty schema `0.8.0` cannot target a zero base because its supported distributions and bounds are strictly positive.

A source-probability target is bounded strictly inside `(0,1)`, so it accepts only Beta or Uniform with `0 < low < high < 1`; its DSA low and high must satisfy the same strict bounds and bracket the base. The engine rejects Gamma, Lognormal, Dirichlet, and endpoint values.

The app checks that `provenance_path` exists, is `distribution_available`, appears in both DSA and PSA input lists, and that every probabilistic `basis_id` belongs to the mapping's evidence sources or proposed assumptions.

## Correlation and omission

Dirichlet sampling preserves dependence within one probability row. Schemas `0.4.0` through `0.8.0` additionally admit bounded cross-parameter dependence only when all of the following hold. Because uncertainty `0.8.0` permits only one excess-rate parameter, it cannot form a multi-member background-mortality group by itself:

- one group contains 2–32 unique scalar parameters and no parameter appears in another group;
- every member already uses `lognormal(mu_log, sigma_log)` with positive `sigma_log`;
- `scale` is `log_standard_normal` and `method` is `cholesky`;
- the matrix order exactly follows `parameter_ids`, is finite and symmetric, has unit diagonal and off-diagonal entries strictly between -1 and 1, and is strictly positive definite under the engine's bounded Cholesky check;
- group `basis_ids` are non-empty and belong to every member distribution's linked evidence or proposed assumptions, with a rationale for the joint estimate.

For each group and PSA iteration, the engine draws independent standard normals in the declared parameter order, left-multiplies them by the lower-triangular Cholesky factor, and applies each member's declared `mu_log` and `sigma_log` before exponentiation. Groups are processed in artifact order, followed by ungrouped parameters in parameter order. The result records the exact groups and matrices.

This matrix represents correlation of the latent standard-normal values on the log scale, not Pearson correlation of the exponentiated model values. AI4HEOR does not convert original-scale correlations, covariance matrices, standard errors, confidence intervals, or posterior samples into this contract. It does not repair a non-positive-definite matrix or infer dependence because parameters share a source. Gamma, beta, uniform, Dirichlet-across-rows, singular or perfect correlation, arbitrary copulas, rank correlation, empirical joint draws, and cross-group dependence remain unsupported.

The plan must justify remaining independence and leave `known_omitted_correlations` empty before review. Known but unsupported dependence remains a blocker; it must not be hidden in prose or removed merely because the current adapter cannot represent it. Every omitted uncertain input needs a provenance path and rationale.

## Reproducibility and convergence

Engine version 0.7 uses versioned `pcg32-xsh-rr` plus fixed beta, gamma, lognormal, uniform, Dirichlet, and bounded lognormal-Cholesky transforms; it supports scheduled matrix rows, structural schedule change points, and deterministic per-draw recomputation of admitted competing-rate, bounded survival, and single-event probability-time transformations. The seed is part of the artifact. Identical inputs produce a bit-identical integer PRNG stream and a repeatable run on the same runtime. Do not claim byte-identical floating-point samples across operating systems until the release matrix passes golden tolerance tests; system math libraries may differ in their final bits.

For legacy two-strategy output, the convergence check records intervention cost-effectiveness probability. For schema `0.7.0`, each checkpoint records every strategy's unique-optimal probability plus a separate tie probability; the gate uses the maximum probability MCSE and maximum drift across that full vector. A pass describes only Monte Carlo error for the sampled run, not independent validation or proof that all uncertainty was represented.

## Decision-threshold and value-of-information contract

Schemas `0.2.0` through `0.10.0` require `probabilistic_analysis.decision_thresholds` with a rationale and 2–101 unique, non-negative, strictly increasing values including the positive primary `willingness_to_pay`. Schema `0.1.0` remains readable and produces one primary-threshold row only. Correlation groups require schema `0.4.0` or later; uncertainty `0.7.0` is reserved for analysis `0.8.0`, uncertainty `0.8.0` for analysis `0.9.0`, uncertainty `0.9.0` for analysis `0.10.0`, and uncertainty `0.10.0` for analysis `0.11.0`.

For each schema `0.7.0` PSA draw and threshold λ, the engine derives every strategy's net monetary benefit `λ × QALY − cost`. It reports:

- each strategy's probability of being the unique optimum and a separate probability of a tie;
- the CEAF probability for the strategy with highest expected net benefit, leaving it null when expected net benefit is tied;
- expected net monetary benefit and probability Monte Carlo standard error by strategy;
- per-person EVPI as `E[max_j NMB_j] − max_j E[NMB_j]`;
- EVPI Monte Carlo standard error from draw-level opportunity loss.

The compact sample artifact records `strategy_order` once and aligned cost/QALY arrays per draw. It does not repeat strategy labels in every sample. Legacy schemas retain the original two-strategy incremental fields for reproducibility.

These are conditional on the current model, declared distributions, dependence handling, and omitted parameters. `population_evpi` and `evppi` remain explicit nulls. Population extrapolation needs separate epidemiology, technology lifetime, discounting, and affected-population inputs; EVPPI needs parameter grouping and validated nested or regression methods. Neither is inferred from the threshold curve.

## Method basis

- [NICE PMG36 economic evaluation, section 4.7](https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2/) requires justified distributions, consideration of correlation, DSA/scenario analyses for drivers, Monte Carlo error review, and CEAC/CEAF presentation across maximum acceptable ICERs.
- [NICE company evidence guide, section 3.11](https://www.nice.org.uk/process/pmg24/chapter/cost-effectiveness) requires parameter values, ranges/distributions and sources, PSA results, CEAC/CEAF, and cost-effectiveness probability.
- [ISPOR-SMDM parameter estimation and uncertainty task-force report](https://www.ispor.org/docs/default-source/resources/outcomes-research-guidelines-index/model_parameter_estimation_and_uncertainty-6.pdf) informs the separation of parameter estimation from uncertainty propagation.
- [NICE DSU TSD 6 on software for probabilistic cost-effectiveness analysis](https://www.sheffield.ac.uk/sites/default/files/2022-02/TSD6-Software.final_.08.05.12.pdf) requires the joint uncertainty structure produced by evidence synthesis to be propagated through the decision model. AI4HEOR implements only the bounded lognormal correlation fragment above, not the document's broader MCMC, multivariate-normal coefficient, bootstrap, or posterior-sample workflows.
- [NICE DSU TSD 14 on survival analysis](https://www.sheffield.ac.uk/sites/default/files/2022-02/TSD14-Survival-analysis.updated-March-2013.v2.pdf) and [TSD 21 on flexible survival models](https://www.sheffield.ac.uk/sites/default/files/2022-02/TSD21-Flex-Surv-TSD-21_Final_alt_text.pdf) support explicit survival parameterization, validity assessment, alternatives, and uncertainty. AI4HEOR implements only propagation through an already-selected exponential or Weibull curve, not fitting, selection, covariance reconstruction, or clinical extrapolation validation.
- [Jones, Epstein, and García-Mochón on transition-rate uncertainty](https://doi.org/10.1177/0272989X17696997) supports connecting rate estimates and their uncertainty directly to probability derivation for auditable DSA and PSA; AI4HEOR retains its narrower competing-first-event transformation instead of converting each competing rate independently.
- [ISPOR-SMDM state-transition good practices](https://www.ispor.org/docs/default-source/resources/outcomes-research-guidelines-index/state-transition_modeling-3.pdf) requires disease/background mortality relationships and double-counting risks to be assessed; additive and multiplicative structures can materially differ. AI4HEOR varies only the additive excess rate and reports the unimplemented multiplicative alternative as structural uncertainty.
- [CDA-AMC economic-evaluation guidelines, 4th edition](https://www.cda-amc.ca/guidelines-economic-evaluation-health-technologies-canada-4th-edition) supports treating general-population mortality as effectively known in many analyses, which is the basis for fixing the declared life table in uncertainty schema `0.8.0`.
- [ISPOR value-of-information methods overview](https://www.ispor.org/publications/journals/value-outcomes-spotlight/vos-archives/issue/view/value-assessments/value-of-information-analysis) distinguishes per-person EVPI available from PSA from population extrapolation, EVPPI, and research-design decisions.
