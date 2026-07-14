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

When at least one input is source-based, bind the exact synthesis bytes at plan root:

```json
"evidence_synthesis": {
  "path": "heor/evidence-synthesis.json",
  "content_sha256": "64-lowercase-hex-digest"
}
```

Add one unique `input_provenance` entry per required path:

```json
{
  "path": "strategies.comparator.state_costs",
  "source_ids": ["cn-cost-study-2025"],
  "extraction_ids": ["extract-comparator-state-costs-2025"],
  "assumption_ids": [],
  "unit": "CNY per cycle by health state",
  "jurisdiction": "China",
  "currency": "CNY",
  "price_year": 2026,
  "monetary_adjustments": [
    {
      "target_index": 0,
      "source_value": 1000.0,
      "source_currency": "CNY",
      "source_price_year": 2026,
      "factor": 1.0,
      "method": "none",
      "basis_ids": []
    },
    {
      "target_index": 1,
      "source_value": 3000.0,
      "source_currency": "CNY",
      "source_price_year": 2026,
      "factor": 1.0,
      "method": "none",
      "basis_ids": []
    },
    {
      "target_index": 2,
      "source_value": 0.0,
      "source_currency": "CNY",
      "source_price_year": 2026,
      "factor": 1.0,
      "method": "none",
      "basis_ids": []
    }
  ],
  "selection_rationale": "Most recent directly applicable Chinese payer-cost study",
  "uncertainty_status": "distribution_available"
}
```

At least one valid source or `proposed` assumption is required. `unit`, `jurisdiction`, and `selection_rationale` are always required. Monetary inputs also require `currency` and integer `price_year` matching the plan's root `economic_basis`. `uncertainty_status` must be `fixed`, `range_available`, or `distribution_available`.

For an array-valued cost input, add exactly one adjustment per array index. For scalar willingness-to-pay, omit `target_index`:

```json
"monetary_adjustments": [
  {
    "target_index": 0,
    "source_value": 920.0,
    "source_currency": "CNY",
    "source_price_year": 2024,
    "factor": 1.0869565217391304,
    "method": "2024-to-2026 health-cost inflation index ratio",
    "basis_ids": ["official-health-cost-index-2026"]
  }
]
```

The validator checks that `source_value * factor` reproduces the exact model value within a small numerical tolerance. `source_currency` uses a three-letter uppercase ISO 4217 format and `source_price_year` ranges from 1900 through 2100. An unchanged value must use factor `1`, method `none`, the same source and model basis, and an empty `basis_ids` array. Any price-year, currency, unit, or numerical adjustment requires a non-`none` method and valid evidence-source or `proposed`-assumption basis IDs. A composite factor is allowed, but the method must describe its inflation, exchange-rate, and unit-conversion components. Keep the underlying rates and dates reviewable in the linked evidence; AI4HEOR does not silently retrieve or choose them.

For every source-based mapping, `extraction_ids` must be a non-empty unique list. Each ID must identify a non-conflicting extraction in the bound synthesis, its `target` must exactly equal the mapping `path`, and its `record_id` must appear in `source_ids`. An assumption-only mapping must not claim extraction IDs.

The portable validator checks the plan, synthesis digest, target, and record links. It cannot read or create the app-owned review chain. AI4HEOR independently requires every selected extraction ID to have current confirmations from two distinct local reviewer labels and no rejection before analysis-plan approval. A single legacy event counts as one confirmation; a rejection blocks the current synthesis version until its bytes are revised and reviewed again.

Structural audit is complete only when all required paths have one valid mapping, no mapping is duplicated or invalid, and no `unresolved` assumptions remain. Human-review readiness additionally requires the dual local-label app review of every selected extraction. This does not prove authenticated identity or independent duplicate extraction. Calculation may still run when incomplete, but analysis-plan approval must fail closed.
