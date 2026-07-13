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
- a complete transition-matrix row.

Supported probabilistic distributions:

- `beta(alpha, beta)` for bounded 0–1 quantities;
- `gamma(shape, scale)` or `lognormal(mu_log, sigma_log)` for positive quantities;
- `uniform(low, high)` only when the evidence supports a bounded uniform assumption;
- `dirichlet(alpha[])` for a complete probability simplex such as a transition row.

The app checks that `provenance_path` exists, is `distribution_available`, appears in both DSA and PSA input lists, and that every probabilistic `basis_id` belongs to the mapping's evidence sources or proposed assumptions.

## Correlation and omission

Dirichlet sampling preserves the dependence within a probability row. Other sampled parameters are independent in engine version 0.1. The plan must justify that assumption and leave `known_omitted_correlations` empty before review. Known but unsupported dependence remains a blocker; it must not be hidden in prose. Every omitted uncertain input needs a provenance path and rationale.

## Reproducibility and convergence

The engine uses versioned `pcg32-xsh-rr` plus fixed beta, gamma, lognormal, uniform, and Dirichlet transforms. The seed is part of the artifact. Identical inputs produce a bit-identical integer PRNG stream and a repeatable run on the same runtime. Do not claim byte-identical floating-point samples across operating systems until the release matrix passes golden tolerance tests; system math libraries may differ in their final bits.

The convergence check records cost-effectiveness probability and its Monte Carlo standard error at each checkpoint. The final MCSE and change from the preceding checkpoint must meet the declared thresholds. A pass describes only the sampled run's Monte Carlo error; it is not independent validation or proof that all uncertainty was represented.

## Method basis

- [NICE PMG36 economic evaluation, section 4.7](https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2/) requires justified distributions, consideration of correlation, DSA/scenario analyses for drivers, and PSA for joint parameter uncertainty.
- [NICE company evidence guide, section 3.11](https://www.nice.org.uk/process/pmg24/chapter/cost-effectiveness) requires parameter values, ranges/distributions and sources, PSA results, and cost-effectiveness probability.
- [ISPOR-SMDM parameter estimation and uncertainty task-force report](https://www.ispor.org/docs/default-source/resources/outcomes-research-guidelines-index/model_parameter_estimation_and_uncertainty-6.pdf) informs the separation of parameter estimation from uncertainty propagation.
