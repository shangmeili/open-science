# Budget impact artifact contract

## Method boundary

The first-party alpha implements a transparent three-year budget-holder cost calculator for exactly two mutually exclusive strategies. It compares `without_new_intervention` and `with_new_intervention`, derives comparator share as one minus intervention share, reports each budget year separately, and applies no discounting.

Use `$heor-dynamic-budget-impact` when annual prevalent/incident entry, exit, displacement, persistence, common mortality, or start capacity is material. Use a future separately admitted cohort or patient-level adapter when disease-severity mix, induced demand, combination treatment, more than two active treatments, partial-cycle events, treatment-specific mortality, or patient history cannot be represented credibly.

## Required artifact

`heor/budget-impact-plan.json` uses schema `0.1.0` and contains:

- `bia_id`, `analysis_id`, and `status`;
- `base_analysis.path` and the exact SHA-256 of `heor/analysis-plan.json`;
- a budget-holder perspective, jurisdiction, currency, price year, and alignment rationale;
- `horizon_years: 3` and `discount_rate: 0`;
- three annual eligible-population values and their derivation;
- comparator/intervention identifiers matching legacy strategy names or selecting two distinct schema `0.8.0` strategy keys;
- three annual new-intervention shares for both market scenarios;
- included intervention and condition-related annual per-patient costs;
- optional scenario-level implementation costs and explicit excluded categories;
- evidence metadata, proposed assumptions, and one unique provenance mapping per required numeric input;
- one-way sensitivity parameters, alternative scenarios, validation plans, and limitations.

## Allowed variation targets

Only these JSON-pointer shapes may be varied:

- `/population/annual_eligible/{0..2}`
- `/market_scenarios/with_new_intervention/intervention_share_by_year/{0..2}`
- `/cost_categories/{index}/annual_per_patient/{comparator|intervention}/{0..2}`
- `/non_patient_costs/{index}/annual_total/{without_new_intervention|with_new_intervention}/{0..2}`

Values must remain finite and non-negative; market shares must remain from zero through one. One-way low/high values bracket the base value. Scenario override targets are unique within each scenario.

## Calculation

For each year and scenario:

`population × ((1 - intervention_share) × comparator_cost + intervention_share × intervention_cost) + scenario_level_costs`

Sum included cost categories before calculating the with-minus-without annual net budget impact. The cumulative result is the undiscounted sum of the three annual impacts. Preserve category-level totals so another analyst can reproduce every result.

## Authority boundary

The artifact may become complete enough for human review but cannot approve itself. The desktop owns approval state and binds the final BIA hash into the analysis-plan approval event. Changes to either file invalidate authorization. Face, internal, and external validation plans are not evidence that validation occurred.

## Governing method sources

- Chinese Pharmaceutical Association, *China Guidelines for Pharmacoeconomic Evaluations 2020*, section 11.
- Chinese Pharmaceutical Association, *China Guidelines for Pharmacoeconomic Evaluations, second edition consultation draft*, section 10; retain as draft methodology context only.
- ISPOR Budget Impact Analysis Good Practice II, Sullivan et al., 2014.

Jurisdiction-specific current guidance governs when it conflicts with the general ISPOR report.
