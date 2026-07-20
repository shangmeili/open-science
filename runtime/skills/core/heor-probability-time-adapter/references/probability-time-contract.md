# Single-event probability time-conversion contract

## Admitted calculation

For source probability `p` over `t_source` years and model cycle `t_cycle`
years, assume a constant instantaneous event rate over the source interval:

```text
r = -log(1 - p) / t_source
p_cycle = 1 - exp(-r * t_cycle)
        = 1 - exp(log(1 - p) * t_cycle / t_source)
```

Require `0 < p < 1`, `t_source > 0`, and `t_cycle > 0`. Use `log1p` and
`expm1` in executable implementations. Do not divide `p` by a cycle count.

## Analysis artifact

Use analysis schema `0.7.0` and map a complete
`strategies.<role>.transition_matrix` or `transition_schedule`. A transformation
has `operation`, the exact `cycle_length_years`, and one or more ordered phases.
Every phase has all state rows. A row contains its `self_index` and either
`event: null` for a structural zero/absorbing row or one event with:

- a distinct valid `target_index`;
- `source_probability` strictly inside `(0,1)`;
- positive `source_interval_years`;
- exactly one `source_extraction_id` plus optional JSON pointer, or one
  `assumption_id` whose status is `proposed`.

The transformation emits only the self and event probabilities; all other row
elements remain structural zero. A static matrix requires one phase. A schedule
starts at cycle 1 and has unique, increasing change points.

## Uncertainty artifact

Use uncertainty schema `0.6.0` and target:

```text
/input_provenance/<mapping>/derivation/transformation/phases/<phase>/rows/<row>/event/source_probability
```

DSA bounds must be finite, increasing, bracket the base, and stay strictly
inside `(0,1)`. PSA accepts Beta or Uniform with `0 < low < high < 1`. The sole
`basis_id` equals the event extraction or proposed-assumption ID. Every
replacement recomputes the complete target transition input and derivation
snapshot before normal model validation. Known dependence remains unresolved;
this contract does not admit correlated probability sampling.

## Method basis

- The ISPOR-SMDM state-transition good-practices report says probabilities
  should be converted between time units through rates and that parameter
  derivation methods and assumptions should be described:
  <https://www.ispor.org/docs/default-source/resources/outcomes-research-guidelines-index/state-transition_modeling-3.pdf>
- PHARMAC's Prescription for Pharmacoeconomic Analysis provides the rate-to-
  probability and inverse formulas and explicitly warns against dividing an
  annual probability by 12 for a monthly cycle:
  <https://www.pharmac.govt.nz/medicine-funding-and-supply/the-funding-process/policies-manuals-and-processes/economic-analysis/prescription-for-pharmacoeconomic-analysis-methods-for-cost-utility-analysis/5-transformation-of-evidence>

These sources support the arithmetic and disclosure requirement. They do not
establish that the constant-hazard assumption or source evidence is appropriate
for a specific decision problem.

## Exclusions

Stop for competing or recurrent events, time-varying hazards, probabilities 0
or 1, multiple transitions within a cycle, conditional or cumulative incidence
with material competing risks, composite endpoints, relative-effect
application inside this adapter, pooling, calibration, survival fitting, background mortality,
time-in-state behavior, or any claim of clinical validity.
Route aligned cycle-specific baseline risks plus RR/OR to
`$heor-relative-effect-adapter`; route HR to the future
`$heor-hazard-ratio-adapter`.
