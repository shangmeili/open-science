# Background-plus-excess mortality contract

## Exact analysis shape

Analysis schema `0.9.0` admits one new operation at a declared strategy transition-schedule path:

```json
{
  "operation": "background_plus_excess_mortality_to_transition_schedule",
  "cycle_length_years": 0.5,
  "from_state_index": 0,
  "death_state_index": 1,
  "life_table": {
    "jurisdiction": "Example jurisdiction",
    "table_year": 2025,
    "population": "General population",
    "sex": "all",
    "start_age_years": 60.0,
    "cycle_probabilities": [
      {
        "cycle": 1,
        "attained_age_years": 60,
        "annual_probability": {
          "value": 0.1,
          "source_extraction_id": "life-table-q-cycle-1",
          "source_pointer": "/q"
        }
      }
    ]
  },
  "excess_mortality_rate_per_year": {
    "value": 0.05,
    "assumption_id": "excess-rate"
  },
  "review_bases": {
    "population_exchangeability": {"assumption_id": "population-exchangeability"},
    "no_double_counting": {"assumption_id": "no-double-counting"}
  }
}
```

The transformation has exactly seven fields. `life_table` has exactly `jurisdiction`, `table_year`, `population`, `sex`, `start_age_years`, and `cycle_probabilities`. Each cycle record has exactly `cycle`, `attained_age_years`, and `annual_probability`. Each probability and the excess rate has a numeric `value` plus exactly one `source_extraction_id` with optional JSON pointer or one `assumption_id`. Each review basis contains exactly one evidence or assumption basis; it contains no value, status, approval, or rationale-as-authority.

The model has exactly two states and uses the two distinct indices 0 and 1. Cycle length may be any finite positive number of years. The cycle list has exactly one-based cycles 1 through the analysis horizon. Attained integer age is:

`floor(start_age_years + (cycle - 1) * cycle_length_years)`.

Repeated attained ages are valid for subannual cycles. Every annual probability remains bound separately so source-table row selection is auditable.

## Formula

For annual life-table death probability `q_age`, constant additive disease excess hazard `h_excess`, and model-cycle length `dt` years:

`h_bg(age) = -ln(1-q_age)`

`p_death(cycle) = 1-exp(-(h_bg(age)+h_excess)*dt)`

Use the stable equivalent `-expm1(dt * (log1p(-q_age) - h_excess))`. The surviving probability is `1-p_death`; death is absorbing. This converts annual probability to an annual hazard before time scaling. Directly multiplying `q_age` by `dt` is invalid.

## Human review and stopping rules

`population_exchangeability` records why the selected table may or may not represent other-cause mortality for the modeled cohort. `no_double_counting` records why disease mortality represented by the excess input is not already contained in another input. These bases expose evidence and assumptions; only the app-owned Human-in-the-loop event can approve the analysis.

Stop and preserve an explicit structural gap when:

- the supplied disease endpoint already represents all-cause mortality;
- cause-specific hazards, cumulative incidence, or subdistribution hazards are mixed;
- calendar mortality improvement is required;
- age or sex mixtures must be weighted rather than one declared table population used;
- excess mortality changes with time, state, treatment, or patient history;
- competing non-death events must share risk in the same row;
- the model is partitioned survival.

The additive and multiplicative/SMR structures can materially differ. AI4HEOR `0.9.0` implements additive excess hazard only. An untested multiplicative structure remains Human-in-the-loop structural uncertainty and a report limitation.

## Uncertainty 0.8.0

Pair analysis `0.9.0` only with uncertainty `0.8.0`. The only transformation parameter target is:

`/input_provenance/<mapping>/derivation/transformation/excess_mortality_rate_per_year/value`

The DSA bounds are strictly positive and bracket the base. PSA uses Gamma, Lognormal, or Uniform with strictly positive lower support and exactly the excess-rate basis. Starting age, table metadata, every annual probability, review bases, operation, and other transformation internals stay fixed. The ordinary structural-scenario contract still requires at least one external scenario. Under uncertainty `0.8.0`, it may replace only a state cost or utility scalar, a discount rate, or half-cycle correction. It may not change cycle count/length, a transition matrix/schedule, the life table, or transformation internals.

## Method basis

- [NICE PMG36 economic evaluation](https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2/) requires population-appropriate mortality, transparent assumptions, uncertainty analysis, and validation.
- [NICE DSU TSD 21](https://sheffield.ac.uk/sites/default/files/2022-02/TSD21-Flex-Surv-TSD-21_Final_alt_text.pdf) discusses expected general-population mortality and warns that comorbidity can make it unsuitable for the patient population.
- [ISPOR-SMDM state-transition good practices](https://www.ispor.org/docs/default-source/resources/outcomes-research-guidelines-index/state-transition_modeling-3.pdf) requires the functional relationship between disease and background mortality to be stated and assessed, and warns about double counting; additive and multiplicative forms can differ materially.
- [CDA-AMC Guidelines for the Economic Evaluation of Health Technologies, 4th edition](https://www.cda-amc.ca/guidelines-economic-evaluation-health-technologies-canada-4th-edition) supports treating general-population mortality as effectively known in many analyses. AI4HEOR therefore holds the life table fixed in the first uncertainty contract while varying only the excess rate.
