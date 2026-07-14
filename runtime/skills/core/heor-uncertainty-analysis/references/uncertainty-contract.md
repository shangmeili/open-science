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

Allowed parameter targets:

- scalar state costs and utilities;
- a complete static transition-matrix row;
- a complete schema `0.4.0` scheduled row at `/strategies/<role>/transition_schedule/<phase>/matrix/<row>`.
- a positive `rate_per_year` for one declared event inside a schema `0.5.0` `constant_competing_rates` transformation, using uncertainty schema `0.3.0`.

Probability-row and schedule-change targets do not apply to a schema `0.5.0` transition derived from constant competing rates. Changing only the derived output makes its deterministic transformation snapshot stale, so the engine rejects it. A rate target must use the exact JSON Pointer `/input_provenance/<mapping>/derivation/transformation/phases/<phase>/rows/<row>/events/<event>/rate_per_year`; its `provenance_path` must equal that indexed mapping's transition path, and its sole `basis_id` must equal the event's `source_extraction_id` or `assumption_id`.

For each DSA run or PSA draw, engine version `0.4.0` applies every sampled rate to an ephemeral plan copy, recomputes each affected transformation once after all replacements, and writes the complete output to both the model transition input and `derivation.model_value` before the normal model validator runs. This preserves row sums, competing-event allocation, derivation integrity, and exact fail-closed validation. It does not admit coordinated transformation-space structural scenarios.

Supported probabilistic distributions:

- `beta(alpha, beta)` for bounded 0–1 quantities;
- `gamma(shape, scale)` or `lognormal(mu_log, sigma_log)` for positive quantities;
- `uniform(low, high)` only when the evidence supports a bounded uniform assumption;
- `dirichlet(alpha[])` for a complete probability simplex such as a transition row.

An event rate is positive but not intrinsically bounded by 1, so it accepts only gamma, lognormal, or uniform with `low > 0`. DSA low/high values must also be positive and bracket the base rate. Beta and Dirichlet are rejected for rate targets.

The app checks that `provenance_path` exists, is `distribution_available`, appears in both DSA and PSA input lists, and that every probabilistic `basis_id` belongs to the mapping's evidence sources or proposed assumptions.

## Correlation and omission

Dirichlet sampling preserves the dependence within a probability row. Other sampled parameters, including multiple event rates, are independent in engine version 0.4. The plan must justify that assumption and leave `known_omitted_correlations` empty before review. Known but unsupported dependence remains a blocker; it must not be hidden in prose. Every omitted uncertain input needs a provenance path and rationale.

## Reproducibility and convergence

Engine version 0.4 uses versioned `pcg32-xsh-rr` plus fixed beta, gamma, lognormal, uniform, and Dirichlet transforms; it supports scheduled matrix rows, structural schedule change points, and deterministic per-draw recomputation of admitted competing-rate transformations. The seed is part of the artifact. Identical inputs produce a bit-identical integer PRNG stream and a repeatable run on the same runtime. Do not claim byte-identical floating-point samples across operating systems until the release matrix passes golden tolerance tests; system math libraries may differ in their final bits.

The convergence check records cost-effectiveness probability and its Monte Carlo standard error at each checkpoint. The final MCSE and change from the preceding checkpoint must meet the declared thresholds. A pass describes only the sampled run's Monte Carlo error; it is not independent validation or proof that all uncertainty was represented.

## Decision-threshold and value-of-information contract

Schemas `0.2.0` and `0.3.0` require `probabilistic_analysis.decision_thresholds` with a rationale and 2–101 unique, non-negative, strictly increasing values. The values must include the positive primary `willingness_to_pay` in the analysis plan. Schema `0.1.0` remains readable and produces one primary-threshold row only; adding a grid to a legacy artifact is rejected rather than silently ignored.

For each PSA draw and threshold λ, the engine derives incremental net monetary benefit `λ × ΔQALY − Δcost`. It reports:

- the probability that the intervention, comparator, or neither uniquely has the higher net benefit;
- the CEAF probability for the strategy with the highest expected net benefit, leaving it null when expected net benefit is tied;
- expected incremental net monetary benefit and probability Monte Carlo standard error;
- per-person EVPI as `E[max(0, incremental NMB)] − max(0, E[incremental NMB])` for the two-strategy model;
- EVPI Monte Carlo standard error from draw-level opportunity loss.

These are conditional on the current model, declared distributions, dependence handling, and omitted parameters. `population_evpi` and `evppi` remain explicit nulls. Population extrapolation needs separate epidemiology, technology lifetime, discounting, and affected-population inputs; EVPPI needs parameter grouping and validated nested or regression methods. Neither is inferred from the threshold curve.

## Method basis

- [NICE PMG36 economic evaluation, section 4.7](https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2/) requires justified distributions, consideration of correlation, DSA/scenario analyses for drivers, Monte Carlo error review, and CEAC/CEAF presentation across maximum acceptable ICERs.
- [NICE company evidence guide, section 3.11](https://www.nice.org.uk/process/pmg24/chapter/cost-effectiveness) requires parameter values, ranges/distributions and sources, PSA results, CEAC/CEAF, and cost-effectiveness probability.
- [ISPOR-SMDM parameter estimation and uncertainty task-force report](https://www.ispor.org/docs/default-source/resources/outcomes-research-guidelines-index/model_parameter_estimation_and_uncertainty-6.pdf) informs the separation of parameter estimation from uncertainty propagation.
- [Jones, Epstein, and García-Mochón on transition-rate uncertainty](https://doi.org/10.1177/0272989X17696997) supports connecting rate estimates and their uncertainty directly to probability derivation for auditable DSA and PSA; AI4HEOR retains its narrower competing-first-event transformation instead of converting each competing rate independently.
- [ISPOR value-of-information methods overview](https://www.ispor.org/publications/journals/value-outcomes-spotlight/vos-archives/issue/view/value-assessments/value-of-information-analysis) distinguishes per-person EVPI available from PSA from population extrapolation, EVPPI, and research-design decisions.
