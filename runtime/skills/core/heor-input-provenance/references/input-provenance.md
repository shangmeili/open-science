# Input provenance contract

The desktop app repeats this audit in Rust. Agent review is explanatory; the application is authoritative for the approval boundary.

## Required input paths

- `cycles`
- `cycle_length_years`
- `discount_rates.costs`
- `discount_rates.outcomes`
- `half_cycle_correction`
- `strategies.comparator.initial_distribution`
- `strategies.comparator.transition_matrix`
- `strategies.comparator.state_costs`
- `strategies.comparator.state_utilities`
- `strategies.intervention.initial_distribution`
- `strategies.intervention.transition_matrix`
- `strategies.intervention.state_costs`
- `strategies.intervention.state_utilities`
- `willingness_to_pay` when it is not null

## Evidence sources

Each source requires:

- `id`: stable within the plan;
- `title` and `source_type`;
- `accessed_on` in ISO date form;
- either `url` or `local_path`;
- `content_sha256` when `local_path` is used.

`published_on` and `supports` are recommended. A URL is a locator, not proof that the source supports a selected value.

## Analyst assumptions

Each assumption contains `id`, `statement`, `reason`, and one status:

- `unresolved`: insufficiently defined and blocks the analysis-plan gate;
- `proposed`: explicit, reviewable analyst choice that can support an input after human review;
- `rejected`: retained for history but cannot support an input.

Do not use `accepted`. Acceptance is represented only by the app-owned approval chain after a human reviews the complete artifact.

## Input mappings

Add one unique `input_provenance` entry per required path:

```json
{
  "path": "strategies.comparator.state_costs",
  "source_ids": ["cn-cost-study-2025"],
  "assumption_ids": [],
  "unit": "CNY per cycle by health state",
  "jurisdiction": "China",
  "price_year": 2025,
  "selection_rationale": "Most recent directly applicable Chinese payer-cost study",
  "uncertainty_status": "distribution_available"
}
```

At least one valid source or `proposed` assumption is required. `unit`, `jurisdiction`, and `selection_rationale` are always required. Monetary inputs also require integer `price_year`. `uncertainty_status` must be `fixed`, `range_available`, or `distribution_available`.

An audit is complete only when all required paths have one valid mapping, no mapping is duplicated or invalid, and no `unresolved` assumptions remain. Calculation may still run when incomplete, but analysis-plan approval must fail closed.
