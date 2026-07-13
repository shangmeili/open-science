# Analysis plan contract

Use `assets/analysis-plan.template.json` as the starting shape. The desktop deterministic engine currently supports one narrow, inspectable cohort state-transition model:

- exactly two strategies: `comparator` and `intervention`;
- one shared set of unique health states;
- time-homogeneous transition matrices;
- state costs and state utilities;
- optional half-cycle correction;
- separate annual discount rates for costs and outcomes;
- optional willingness-to-pay threshold for net monetary benefit.

## Required engine fields

`schema_version` must be `0.1.0`. `analysis_id` must be non-empty. `reference_case` contains a registered `id` and its exact `status`. `states`, `cycles`, `cycle_length_years`, `discount_rates`, `half_cycle_correction`, and `strategies` are required.

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

Use `$heor-input-provenance` and its reference contract for exact fields. Each required model input must map to valid evidence or an explicit `proposed` analyst assumption. `unresolved` assumptions block analysis-plan approval. Never write `accepted`; canonical acceptance exists only in the app-owned human approval chain.

## Reference-case profiles

The packaged registry currently exposes `CN-2020-current` and `CN-2026-draft`. Registry entries are metadata pointers, not encoded compliance checks. Selecting either profile does not establish guideline compliance; a `draft` profile also prevents local analysis authorization.

## Artifact stability

The app hashes the exact saved bytes. After a human approves a gate, any file change produces a different artifact and requires renewed review. Format deliberately and avoid unrelated rewrites after approval.
