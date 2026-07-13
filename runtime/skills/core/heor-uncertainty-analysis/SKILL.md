---
name: heor-uncertainty-analysis
description: Create and audit a hash-bound HEOR uncertainty plan for deterministic one-way sensitivity analysis, probabilistic sensitivity analysis, Monte Carlo convergence, parameter dependence, and structural scenarios. Use when preparing or repairing heor/uncertainty-plan.json, converting evidence ranges or distributions into executable model inputs, explaining uncertainty drivers, or preparing the analysis-plan human gate without claiming validation or decision certainty.
---

# HEOR Uncertainty Analysis

Create a reproducible local uncertainty artifact; do not generate ad hoc simulation code. Read `references/uncertainty-contract.md` before creating or changing the artifact.

## Workflow

1. Read `heor/analysis-plan.json`, its `input_provenance`, and `heor/conceptual-model.json`. Use the current exact bytes, not a remembered plan.
2. Confirm a positive willingness-to-pay value and a fixed `uncertainty_analysis.path` of `heor/uncertainty-plan.json` in the analysis plan.
3. Select parameter targets only from the engine allowlist. Link each target to one `distribution_available` provenance mapping. Do not invent a range, distribution, or dependence assumption from a point estimate.
4. Record one-way low/high values that bracket the base value and explain their evidence basis. Use coherent complete transition rows rather than changing a single probability independently.
5. Choose an evidence-compatible distribution. Record basis IDs from the linked provenance mapping and explain the parameterization. Use Dirichlet for a complete transition row.
6. State the independence rationale and resolve known omitted correlations. List PSA omissions with a reason; omission is visible, not silently converted to fixed certainty.
7. Set an explicit unsigned 64-bit seed, 1,000–10,000 iterations, at least two increasing convergence checkpoints ending at the iteration count, and probability MCSE/drift thresholds no greater than 0.1. The first-party desktop caps iterations because it returns auditable per-draw output; larger production runs require a future streamed artifact format, not an unbounded response.
8. Define at least one bounded structural scenario with allowlisted replacements and a rationale. Keep structural uncertainty separate from parameter uncertainty.
9. Write `heor/uncertainty-plan.json` from the bundled template. Bind `base_analysis.content_sha256` to the final exact bytes of `heor/analysis-plan.json`.
10. Run `scripts/validate_uncertainty_plan.py`. The desktop repeats and extends the audit before approval or execution.

## Boundaries

- Never create approval events, accept analyst assumptions, or claim independent validation.
- Never change identifiers, reference-case status, evidence, approvals, or file paths through an uncertainty target.
- Do not report a seeded run as generally converged merely because it completed. Report its checkpoint diagnostic and thresholds.
- Do not treat DSA as a substitute for joint PSA in a nonlinear model.
- Do not treat cost-effectiveness probability as a recommendation or policy threshold decision.
- Preserve unsupported distributions, correlations, and structural uncertainty as explicit blockers or limitations.

## Handoff

Report the analysis and uncertainty IDs, exact plan and uncertainty hashes, PRNG algorithm/version, seed, parameter and scenario counts, PSA iterations, omitted parameters, correlation handling, convergence result, blocking errors, and the next natural-language repair. Distinguish calculation reproducibility from methodological validity.
