---
name: heor-uncertainty-analysis
description: Create and audit a hash-bound HEOR uncertainty plan for deterministic one-way sensitivity analysis, probabilistic sensitivity analysis, evidence-bound lognormal correlation groups, CEAC, CEAF, per-person EVPI, Monte Carlo convergence, and structural scenarios. Use when preparing or repairing heor/uncertainty-plan.json, converting evidence ranges, joint log-scale estimates, or distributions into executable model inputs, explaining decision uncertainty or value of information, or preparing the analysis-plan human gate without claiming validation, population EVPI, research priority, or decision certainty.
---

# HEOR Uncertainty Analysis

Create a reproducible local uncertainty artifact; do not generate ad hoc simulation code. Read `references/uncertainty-contract.md` before creating or changing the artifact.

## Workflow

1. Read `heor/analysis-plan.json`, its `input_provenance`, and `heor/conceptual-model.json`. Use the current exact bytes, not a remembered plan.
2. Confirm a positive willingness-to-pay value and a fixed `uncertainty_analysis.path` of `heor/uncertainty-plan.json` in the analysis plan.
3. Select parameter targets only from the engine allowlist. Link each target to one `distribution_available` provenance mapping. Do not invent a range, distribution, or dependence assumption from a point estimate. Use current uncertainty schema `0.4.0`; schemas `0.1.0` through `0.3.0` remain readable for reproducibility.
4. Record one-way low/high values that bracket the base value and explain their evidence basis. Use coherent complete transition rows rather than changing a single probability independently; scheduled rows use `/strategies/<role>/transition_schedule/<phase>/matrix/<row>`.
5. Choose an evidence-compatible distribution. Record basis IDs from the linked provenance mapping and explain the parameterization. Use Dirichlet for a complete transition row.
6. For an admitted schema `0.5.0` constant competing-rate transformation, target only one exact event rate at `/input_provenance/<mapping>/derivation/transformation/phases/<phase>/rows/<row>/events/<event>/rate_per_year`. Require positive DSA bounds and gamma, lognormal, or strictly positive uniform PSA values. Bind `basis_ids` to exactly that event's extraction or proposed assumption. The engine recomputes the affected complete matrix or schedule after all rate draws; never target its derived probability row.
7. State the independence rationale and resolve known omitted correlations. When evidence supplies a joint log-scale correlation estimate, declare a schema `0.4.0` group of 2–32 scalar `lognormal` parameters with fixed `log_standard_normal` scale, `cholesky` method, a symmetric strictly positive-definite correlation matrix, linked basis IDs, and rationale. A parameter belongs to at most one group. Do not estimate, repair, or guess a correlation matrix. List PSA omissions with a reason; omission is visible, not silently converted to fixed certainty.
8. Set an explicit unsigned 64-bit seed, 1,000–10,000 iterations, at least two increasing convergence checkpoints ending at the iteration count, and probability MCSE/drift thresholds no greater than 0.1. The first-party desktop caps iterations because it returns auditable per-draw output; larger production runs require a future streamed artifact format, not an unbounded response.
9. Declare 2–101 unique increasing, non-negative decision thresholds and a rationale. Include the analysis plan's primary willingness-to-pay value. Derive the range from an explicit decision context or human instruction; never invent a jurisdictional threshold. The engine uses the same PSA draws to calculate the intervention CEAC, two-strategy CEAF, and per-person EVPI at every threshold.
10. Define at least one bounded structural scenario with allowlisted replacements and a rationale. A schema `0.4.0` schedule change point may be varied through `/strategies/<role>/transition_schedule/<phase>/start_cycle`, but the resulting model must remain ordered and in horizon. Keep structural uncertainty separate from parameter uncertainty.
11. Write schema `0.4.0` `heor/uncertainty-plan.json` from the bundled template. Bind `base_analysis.content_sha256` to the final exact bytes of `heor/analysis-plan.json`. Schema `0.3.0` remains readable and admits event-rate targets but not correlation groups; `0.2.0` retains threshold grids; `0.1.0` evaluates only the primary threshold.
12. Run `scripts/validate_uncertainty_plan.py`. The desktop repeats and extends the audit before approval or execution.

## Boundaries

- Never create approval events, accept analyst assumptions, or claim independent validation.
- Never change identifiers, reference-case status, evidence, approvals, or file paths through an uncertainty target.
- Do not report a seeded run as generally converged merely because it completed. Report its checkpoint diagnostic and thresholds.
- Do not treat DSA as a substitute for joint PSA in a nonlinear model.
- Do not use beta or Dirichlet for event rates, change a derived probability row, or describe independent draws as correlated. Only evidence-bound lognormal members may enter a correlation group; gamma, beta, uniform, Dirichlet, cross-group, singular, perfect, empirical-draw, copula, and rank-correlation dependence remain unsupported. Resolve known omitted correlations before review.
- Do not use rate targets for probability time conversion, HR/RR/OR application, pooling, extrapolation, general CTMC intensities, or transformation-space structural scenarios.
- Do not treat cost-effectiveness probability as a recommendation or policy threshold decision.
- Report CEAC and CEAF separately: the intervention's probability of being optimal is not always the probability that the strategy with the highest expected net benefit is optimal.
- Treat EVPI as a per-person upper bound over uncertainty represented in the current PSA only. Do not extrapolate it to a population without explicit eligible population, incidence/prevalence, time horizon, technology lifetime, and discounting inputs.
- Do not claim EVPPI, expected value of sample information, optimal study design, or a research-funding recommendation from this engine.
- Preserve unsupported distributions, correlations, and structural uncertainty as explicit blockers or limitations.

## Handoff

Report the analysis and uncertainty IDs, exact plan and uncertainty hashes, PRNG algorithm/version, seed, parameter, correlation-group, threshold, and scenario counts, PSA iterations, CEAC/CEAF at the declared thresholds, primary-threshold per-person EVPI and its Monte Carlo standard error, omitted parameters, correlation handling and evidence bases, convergence result, blocking errors, and the next natural-language repair. Distinguish calculation reproducibility from methodological validity and leave population EVPI/EVPPI explicitly uncalculated.
