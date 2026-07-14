# Analysis plan contract

Use `assets/analysis-plan.template.json` as the starting shape. The desktop deterministic engine currently supports one narrow, inspectable cohort state-transition model:

- exactly two strategies: `comparator` and `intervention`;
- one shared set of unique health states;
- time-homogeneous transition matrices;
- state costs and state utilities;
- optional half-cycle correction;
- separate annual discount rates for costs and outcomes;
- optional willingness-to-pay threshold for net monetary benefit.
- one declared calculation currency and price year for every monetary result.

## Required engine fields

`schema_version` must be `0.2.0` for a new or approvable plan. `analysis_id` must be non-empty. `economic_basis` must contain a three-letter uppercase ISO 4217-format `currency` and an integer `price_year` from 1900 through 2100. Replace the template's China example when another jurisdiction or valuation basis applies. `reference_case` contains a registered `id` and its exact `status`. `states`, `cycles`, `cycle_length_years`, `discount_rates`, `half_cycle_correction`, and `strategies` are required.

The engine can still calculate a legacy `0.1.0` plan for reproducibility, but its result has no claimed currency or price-year basis and remains exploratory. The app refuses analysis-plan approval until the plan uses `0.2.0` and every monetary input passes the normalization audit.

The complete MVP plan also fixes `uncertainty_analysis.path` to `heor/uncertainty-plan.json` and `budget_impact_analysis.path` to `heor/budget-impact-plan.json`. The analysis-plan approval binds the exact hashes of both sibling artifacts. Their detailed numeric contracts stay outside this file.

For each strategy:

- `initial_distribution` length equals the number of states and sums to 1;
- `transition_matrix` is square and every row sums to 1;
- `state_costs` and `state_utilities` lengths equal the number of states;
- probabilities and utilities are finite values from 0 through 1;
- costs are finite and non-negative.

The engine rejects an `approvals` field. Human approval state lives outside the workspace.

## Review metadata

Keep the `decision_problem`, `evidence_sources`, `assumptions`, `input_provenance`, and `input_status` metadata. The numerical engine ignores these fields, while the app independently audits them before analysis-plan approval.

Use `$heor-input-provenance` and its reference contract for exact fields. Each required model input must map to valid evidence or an explicit `proposed` analyst assumption. Every state cost and non-null willingness-to-pay value must declare the plan currency and price year, then reproduce each model value from a recorded source value and adjustment factor. `unresolved` assumptions block analysis-plan approval. Never write `accepted`; canonical acceptance exists only in the app-owned human approval chain.

## Reference-case profiles

The packaged registry currently exposes `CN-2020-current`, `CN-2026-draft`, and `NICE-PMG36-2026-current`. Registry entries are versioned executable subsets, not copies of guidance or compliance certificates. Selecting any profile does not establish guideline compliance; a `draft` profile also prevents local analysis authorization. NICE analyses must standardize the jurisdiction as `England`, state the NHS and personal social services perspective, use the profile's discounting rule, and populate `methodology.health_outcomes` for the app-owned reference-case audit.

## Artifact stability

The app hashes the exact saved bytes. After a human approves a gate, any file change produces a different artifact and requires renewed review. Format deliberately and avoid unrelated rewrites after approval.
