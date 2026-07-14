# Input provenance contract

The desktop app repeats this audit in Rust. Agent review is explanatory; the application is authoritative for the approval boundary.

## Required input paths

- `cycles`
- `cycle_length_years`
- `discount_rates.costs`
- `discount_rates.outcomes`
- `half_cycle_correction`
- for every schema `0.8.0` or `0.9.0` ID in `strategy_order`, or both legacy roles `comparator` and `intervention`:
  - `strategies.<strategy_id>.initial_distribution`
  - exactly one of `strategies.<strategy_id>.transition_matrix` or `strategies.<strategy_id>.transition_schedule`
  - `strategies.<strategy_id>.state_costs`
  - `strategies.<strategy_id>.state_utilities`
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
  "derivation": {
    "method": "monetary_adjustment",
    "model_value": [1000.0, 3000.0, 0.0]
  },
  "monetary_adjustments": [
    {
      "target_index": 0,
      "source_extraction_id": "extract-comparator-state-costs-2025",
      "source_index": 0,
      "source_value": 1000.0,
      "source_currency": "CNY",
      "source_price_year": 2026,
      "factor": 1.0,
      "method": "none",
      "basis_ids": []
    },
    {
      "target_index": 1,
      "source_extraction_id": "extract-comparator-state-costs-2025",
      "source_index": 1,
      "source_value": 3000.0,
      "source_currency": "CNY",
      "source_price_year": 2026,
      "factor": 1.0,
      "method": "none",
      "basis_ids": []
    },
    {
      "target_index": 2,
      "source_extraction_id": "extract-comparator-state-costs-2025",
      "source_index": 2,
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

Approvable portable analysis-plan schemas `0.3.0` through `0.9.0` require a `derivation` on every mapping. Schema `0.8.0` retains the admitted bounded transition transformations at `strategies.<strategy_id>...` paths and adds dynamic multi-strategy enumeration. Schema `0.9.0` adds the background-mortality transformation below. A transition schedule maps the complete array instead of the absent static matrix. `derivation.model_value` is a redundant review snapshot that must equal the exact current value at `path`; changing either side invalidates the mapping.

Use only these executable methods:

- `direct_evidence`: exactly one selected extraction; its `extracted_value` must parse as strict JSON and equal the complete model value. For example, `[0.8,0.5,0]` can directly support a state-utility vector, while `0.8, 0.5 and 0 with caveats` cannot.
- `explicit_assumption`: no source or extraction IDs, at least one linked `proposed` assumption, and a snapshot equal to the model value.
- `monetary_adjustment`: source-based state costs or willingness-to-pay, with each source value bound to a selected extraction and then arithmetically normalized.
- `deterministic_transformation`: a schema `0.5.0` matrix or schedule derived by `$heor-transition-rate-adapter` from constant cause-specific competing event rates; a schema `0.6.0` complete per-cycle two-state schedule derived by `$heor-survival-curve-adapter` from one declared exponential or Weibull curve; a schema `0.7.0` complete matrix or schedule derived by `$heor-probability-time-adapter` from at most one event per row with an explicit source interval and reviewable constant-hazard assumption; or a schema `0.9.0` two-state schedule derived by `$heor-background-mortality` from age-aligned annual general-population all-cause probabilities, any finite positive model-cycle length, and one constant additive disease excess rate. Every numeric parameter binds exactly one extraction or proposed assumption, and the validator independently recomputes the complete output.

The schema `0.9.0` operation is exactly `background_plus_excess_mortality_to_transition_schedule`. Its exact transformation fields are `operation`, `cycle_length_years`, `from_state_index`, `death_state_index`, `life_table`, `excess_mortality_rate_per_year`, and `review_bases`. `life_table` records jurisdiction, table year, population, sex, start age, and one exact cycle record per model cycle; every record contains `cycle`, `attained_age_years = floor(start_age_years + (cycle - 1) * cycle_length_years)`, and evidence-bound `annual_probability`. Each cycle computes `h_bg = -ln(1-q_annual)`, then `p_death = 1-exp(-(h_bg+h_excess)*cycle_length_years)`. Every annual probability and the excess rate requires one extraction or proposed-assumption basis. `review_bases` contains exactly `population_exchangeability` and `no_double_counting`, each as one basis only. The contract rejects approval/status/rationale fields there: evidence about exchangeability or double counting does not replace app-owned human approval.

Do not place a probability conversion, pooling rule, matrix assembly, calibration, interpolation, or other formula only in `selection_rationale`. The contract evaluates only the admitted structured transformations above. Keep every other mapping incomplete until a bounded deterministic adapter supports it. The background-mortality route must stop for already all-cause mortality, cause-specific/subdistribution mixing, calendar mortality improvement, age/sex mixtures, time-varying excess hazards, competing non-death events, and partitioned survival. Additive and multiplicative structures may materially differ; only additive excess hazard is admitted.

An assumption-only mapping is explicit and executable at the artifact level:

```json
{
  "path": "cycles",
  "source_ids": [],
  "extraction_ids": [],
  "assumption_ids": ["assumption-three-year-horizon"],
  "unit": "annual cycles",
  "jurisdiction": "China",
  "derivation": {
    "method": "explicit_assumption",
    "model_value": 3
  },
  "selection_rationale": "Explicit horizon assumption pending human plan approval",
  "uncertainty_status": "fixed"
}
```

For an array-valued cost input, add exactly one adjustment per model array index. When the bound extraction contains a JSON array, also set `source_index`; when it contains a JSON scalar, omit `source_index`. For scalar willingness-to-pay, omit `target_index`:

```json
"monetary_adjustments": [
  {
    "target_index": 0,
    "source_extraction_id": "extract-comparator-state-costs-2024",
    "source_index": 0,
    "source_value": 920.0,
    "source_currency": "CNY",
    "source_price_year": 2024,
    "factor": 1.0869565217391304,
    "method": "2024-to-2026 health-cost inflation index ratio",
    "basis_ids": ["official-health-cost-index-2026"]
  }
]
```

For source-based monetary inputs, every adjustment also names `source_extraction_id`; every selected extraction must be used. The validator parses the extraction's strict JSON scalar or indexed array element, verifies that it equals `source_value`, and then checks that `source_value * factor` reproduces the exact model value within a small numerical tolerance. Assumption-only monetary inputs must not claim source-extraction bindings.

`source_currency` uses a three-letter uppercase ISO 4217 format and `source_price_year` ranges from 1900 through 2100. An unchanged value must use factor `1`, method `none`, the same source and model basis, and an empty `basis_ids` array. Any price-year, currency, unit, or numerical adjustment requires a non-`none` method and valid evidence-source or `proposed`-assumption basis IDs. A composite factor is allowed, but the method must describe its inflation, exchange-rate, and unit-conversion components. Keep the underlying rates and dates reviewable in the linked evidence; AI4HEOR does not silently retrieve or choose them.

For every source-based mapping, `extraction_ids` must be a non-empty unique list. Each ID must identify a non-conflicting extraction in the bound synthesis, its `target` must exactly equal the mapping `path`, and its `record_id` must appear in `source_ids`. An assumption-only mapping must not claim extraction IDs.

The portable validator checks the plan, synthesis digest, target, record links, strict extracted JSON, derivation snapshots, direct-value equality, monetary source bindings, and normalization arithmetic. It cannot read or create the app-owned review chain. The native desktop repeats these derivation checks against the current workspace synthesis and independently requires every selected extraction ID to have current confirmations from two distinct local reviewer labels and no rejection before analysis-plan approval. A single legacy event counts as one confirmation; a rejection blocks the current synthesis version until its bytes are revised and reviewed again.

Structural audit is complete only when the plan uses approvable portable schema `0.3.0` through `0.9.0`, all required paths for every declared strategy have one valid executable mapping, no mapping is duplicated or invalid, and no `unresolved` assumptions remain. Schema `0.1.0` and `0.2.0` remain calculation-only for reproducibility and cannot pass approval. Human-review readiness additionally requires the dual local-label app review of every selected extraction. This does not prove authenticated identity, source truth, population exchangeability, absence of double counting, substantive appropriateness of a transformation, or independent duplicate extraction. Calculation may still run when incomplete, but analysis-plan approval must fail closed.
