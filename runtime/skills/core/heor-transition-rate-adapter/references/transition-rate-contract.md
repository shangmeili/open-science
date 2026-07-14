# Constant competing-rate transformation contract

## Admitted method

For a row with constant cause-specific event rates `r_i` over a model cycle of `t` years:

- `R = sum(r_i)`
- total event probability `p_event = 1 - exp(-R * t)`
- event probability `p_i = (r_i / R) * p_event`
- probability of remaining in the source state `p_stay = exp(-R * t)`

When `R = 0`, the row is an identity row. Computations use the numerically stable equivalent `-expm1(-R * t)` for total event probability.

This is a bounded competing-first-event transformation. It assumes rates are constant within a phase and at most one state change occurs within a cycle. It is not a general continuous-time Markov-chain matrix exponential and does not model paths containing multiple within-cycle transitions.

## Provenance shape

The mapping path must be one of the two strategy `transition_matrix` or `transition_schedule` paths. The derivation must have this shape:

```json
{
  "method": "deterministic_transformation",
  "model_value": [[0.8, 0.2], [0.0, 1.0]],
  "transformation": {
    "operation": "constant_competing_rates",
    "cycle_length_years": 1.0,
    "phases": [{
      "start_cycle": 1,
      "rows": [{
        "self_index": 0,
        "events": [{
          "target_index": 1,
          "rate_per_year": 0.22314355131420976,
          "source_extraction_id": "mortality-rate",
          "source_pointer": "/0"
        }]
      }, {
        "self_index": 1,
        "events": []
      }]
    }]
  }
}
```

Each event declares exactly one `source_extraction_id` or `assumption_id`. `source_pointer` is optional for a scalar and otherwise is a JSON pointer into the strict-JSON extracted value. Rates must be finite and positive; omit structural-zero events. Target indices are unique and cannot equal `self_index`.

The phase row count equals the health-state count, `self_index` equals the zero-based row position, phase 1 starts at model cycle 1, and later starts strictly increase within the horizon. A static matrix has exactly one phase. A schedule emits a complete matrix for every phase.

The transformation cycle length must equal `analysis-plan.cycle_length_years`. The recomputed output must equal the current transition input and `derivation.model_value` within deterministic numerical tolerance. Every mapping-level extraction and assumption ID must be used by the transformation and no undeclared ID may be used.

## Rate-space uncertainty

Uncertainty schema `0.3.0` or `0.4.0` may vary one or more declared event rates through an exact target:

```text
/input_provenance/<mapping>/derivation/transformation/phases/<phase>/rows/<row>/events/<event>/rate_per_year
```

The target must resolve to a positive base rate in an analysis schema `0.5.0` mapping whose method and operation are exactly those above. `provenance_path` equals the indexed mapping path. The parameter has exactly one `basis_id`, equal to the event's `source_extraction_id` or `assumption_id`. DSA bounds are finite, positive, increasing, and bracket the base. PSA uses gamma, lognormal, or uniform with a strictly positive lower bound; rates are not probabilities, so beta and Dirichlet are invalid.

After all parameter values for one run are applied, the engine recomputes each affected transformation once, replaces the complete matrix or schedule, updates `derivation.model_value`, and invokes normal analysis-plan validation. Multiple declared rates can therefore preserve their competing allocation within a row. Schema `0.4.0` may jointly sample 2–32 lognormal rate parameters through an evidence-bound `log_standard_normal` Cholesky correlation group. The declared matrix is latent log-scale correlation, not correlation of exponentiated rates. Gamma, uniform, singular/perfect, copula, empirical-draw, and unsupported cross-group rate dependence remain blockers rather than inferred capability.

## Evidence and method basis

- ISPOR-SMDM state-transition good-practice guidance requires rates and probabilities to be used appropriately, probability derivations to be described, and cycle length to be short enough for the modeled event semantics: <https://www.ispor.org/docs/default-source/resources/outcomes-research-guidelines-index/state-transition_modeling-3.pdf>
- PHARMAC explains the single-rate relationship `p = 1 - exp(-r*t)` and requires probabilities to match model-cycle length: <https://www.pharmac.govt.nz/assets/5-transformation-of-evidence-2059.pdf>. AI4HEOR does not apply that formula separately to competing causes; it uses the total-rate allocation above.
- Welton and colleagues show why conversions become more complex in multi-state systems; this adapter therefore does not claim general CTMC conversion: <https://www.repository.cam.ac.uk/items/5ddd5a9c-483a-4fe0-9f03-dda1bd248f8d>
- Jones, Epstein, and García-Mochón show the audit advantage of propagating uncertainty from rates through probability derivation: <https://doi.org/10.1177/0272989X17696997>. This supports the data flow, not a broader multi-state method claim.

## Unsupported inputs

Keep the mapping incomplete and explain the required future adapter when the source supplies only cumulative probability at another time unit, hazard/risk/odds ratios, survival curves, time-varying hazards within a phase, transition intensities with material multi-step paths, competing outcomes that are not mutually exclusive, correlated rate uncertainty, or a structural scenario that changes transformation shape or timing.
