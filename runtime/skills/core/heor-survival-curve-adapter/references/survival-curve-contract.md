# Parametric survival-to-transition contract

## Admitted method

For model-cycle boundaries `t_i = i * cycle_length_years`, the event probability from the origin state in cycle `i` is `p_i = 1 - exp(-(H(t_i) - H(t_(i-1))))`. AI4HEOR computes the numerically stable equivalent `-expm1(-delta_H)`.

- exponential: `H(t) = rate_per_year * t`
- Weibull scale/shape: `H(t) = (t / scale_years) ^ shape`

All parameters and times are positive and expressed in years. The Weibull definition above is the only admitted parameterization. Each generated two-state matrix preserves the origin or moves it to the absorbing event state; the event-state row is absorbing.

## Provenance shape

Use analysis schema `0.6.0` and map a complete strategy transition schedule:

```json
{
  "method": "deterministic_transformation",
  "model_value": [{"start_cycle": 1, "matrix": [[0.8, 0.2], [0.0, 1.0]]}],
  "transformation": {
    "operation": "parametric_survival_to_transition_schedule",
    "cycle_length_years": 1.0,
    "from_state_index": 0,
    "event_state_index": 1,
    "distribution": "exponential",
    "parameters": {
      "rate_per_year": {
        "value": 0.22314355131420976,
        "source_extraction_id": "mortality-rate",
        "source_pointer": "/rate"
      }
    }
  }
}
```

Exponential declares exactly `rate_per_year`. Weibull declares exactly `shape` and `scale_years`. Each parameter has exactly one `source_extraction_id` or `assumption_id`. `source_pointer` is optional for scalar strict JSON and otherwise resolves into the selected extraction. Mapping-level extraction and assumption IDs must exactly equal the parameter bases.

The analysis has exactly two states and 1–10,000 cycles. The transformation cycle length equals the analysis cycle length. The adapter emits a complete schedule entry for every cycle, beginning at cycle 1. The independently recomputed schedule must equal the current model input and `derivation.model_value` within deterministic numeric tolerance.

## Parameter-uncertainty contract

Uncertainty schema `0.5.0` or `0.6.0` may vary an exact positive curve parameter through one of these JSON Pointers:

- `/input_provenance/<mapping>/derivation/transformation/parameters/rate_per_year/value` for exponential;
- `/input_provenance/<mapping>/derivation/transformation/parameters/shape/value` or `/scale_years/value` for Weibull.

The pointer must match the indexed analysis schema `0.6.0` survival mapping and declared distribution. `provenance_path` equals that mapping's complete schedule path. The uncertainty parameter's sole `basis_id` equals the curve parameter's `source_extraction_id` or `assumption_id`. DSA bounds are finite, positive, increasing, and bracket the base. PSA accepts gamma, lognormal, or uniform with `low > 0`; beta and Dirichlet are invalid.

For each DSA run or PSA draw, uncertainty engine `0.7.0` applies all replacements to an ephemeral plan, recomputes each affected complete schedule once, updates `derivation.model_value`, and invokes the ordinary analysis validator. This propagates declared parameter uncertainty through every cycle without granting authority to fit, select, or clinically validate the curve. Alternative curve families and parameterizations remain structural questions outside this scalar target.

## Method and delivery basis

- NICE PMG36 requires survival extrapolation to assess internal and external validity, use clinically plausible alternatives, and explore uncertainty: <https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2/>
- NICE DSU TSD 14 covers parametric survival analysis for economic evaluation: <https://www.sheffield.ac.uk/sites/default/files/2022-02/TSD14-Survival-analysis.updated-March-2013.v2.pdf>
- NICE DSU TSD 21 covers flexible survival models when standard parametric assumptions are inadequate: <https://www.sheffield.ac.uk/sites/default/files/2022-02/TSD21-Flex-Surv-TSD-21_Final_alt_text.pdf>

These sources support explicit parameterization, alternatives, validity checks, and uncertainty; they do not justify automatic curve choice. AI4HEOR therefore admits deterministic evaluation and evidence-bound parameter propagation for an already-selected curve, while recording wider survival-analysis work as unresolved until separately implemented and reviewed.

## Unsupported inputs

Stop and preserve an explicit gap when work requires curve fitting or automatic model selection; deriving marginal distributions or covariance from incomplete fit output; Kaplan-Meier digitization or individual-patient-data reconstruction; fractional-polynomial, spline, cure, mixture, or dependent competing-risk models; PFS/OS partitioned survival; treatment-effect or hazard-ratio application; background mortality; multiple event endpoints; time-dependent covariates; transformation-space structural scenarios; or a claim that extrapolation is clinically valid.
