# Cohort state-transition model contract

## Selection boundary

Use a cohort state-transition model when the decision problem can be represented by a closed cohort, a manageable set of mutually exclusive and collectively exhaustive states, and no interaction between people. Relevant history must either be unnecessary or represented transparently in the state structure. If time in state, prior events, continuously varying patient attributes, dynamic treatment rules, or interactions materially determine transitions or rewards, this bounded engine is not an adequate substitute for a semi-Markov, individual-level, discrete-event, or dynamic model.

Method basis:

- [ISPOR-SMDM state-transition good practices](https://www.ispor.org/publications/journals/value-in-health/abstract/Volume-15--Issue-6/State-Transition-Modeling--A-Report-of-the-ISPOR-SMDM-Modeling-Good-Research-Practices-Task-Force-3) recommends choosing cohort simulation only when relevant characteristics and histories can be represented with manageable states. It identifies time-dependent parameters as a reason to use a state-transition approach.
- [NICE PMG36 economic evaluation](https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2) requires transparent, decision-problem-specific model structure, documented inputs, appropriate time horizon, alternative extrapolation scenarios, uncertainty analysis, and validation.

These sources support the review questions; they do not certify an AI4HEOR model.

## Executable transition contract

Analysis schemas `0.4.0` through `0.8.0` accept exactly one transition mechanism for each strategy:

```json
"transition_matrix": [
  [0.90, 0.10],
  [0.00, 1.00]
]
```

or:

```json
"transition_schedule": [
  {"start_cycle": 1, "matrix": [[0.95, 0.05], [0.00, 1.00]]},
  {"start_cycle": 4, "matrix": [[0.90, 0.10], [0.00, 1.00]]}
]
```

Rules:

- `start_cycle` is one-based model time.
- The first phase starts at cycle 1.
- Change points are unique, strictly increasing integers no greater than `cycles`.
- A phase remains active until the next change point; the last phase remains active through the horizon.
- Every matrix is square with one row and column per health state.
- Every value is finite and from 0 through 1; every row sums to 1 within engine tolerance.
- Initial distributions sum to 1. The engine verifies cohort-mass conservation after every cycle.
- Rewards retain the existing start-of-cycle or half-cycle-corrected semantics. Transition schedules do not change state costs or utilities.
- Schema `0.3.0` remains valid for static matrices. Schedules require schema `0.4.0` or later. Schema `0.8.0` admits the existing bounded transition transformations at dynamic strategy paths and requires 2–16 explicitly ordered strategies.

The result records `transition_mode` as `static` or `piecewise_by_model_cycle` and reports the effective schedule start cycles. The exact input bytes remain the authoritative record of matrices.

## Evidence and uncertainty

Map a static matrix at `strategies.<role>.transition_matrix`. Map a schedule at `strategies.<role>.transition_schedule`. The derivation snapshot must equal the complete current value. A direct-evidence extraction must contain strict JSON equal to that complete matrix or schedule. Constant cause-specific competing event rates may be transformed only through `$heor-transition-rate-adapter`; an already-selected exponential or Weibull two-state survival curve may be evaluated only through `$heor-survival-curve-adapter`; a single event probability with an explicit source interval may be converted only through `$heor-probability-time-adapter`. Other assembly from several estimates remains incomplete.

Allowed uncertainty row targets are:

```text
/strategies/<role>/transition_matrix/<row>
/strategies/<role>/transition_schedule/<phase>/matrix/<row>
```

Use a coherent complete simplex for deterministic bounds and a Dirichlet distribution for PSA. A structural scenario may change an allowlisted schedule `start_cycle`; the resulting complete model must still pass ordering and horizon validation. Do not vary one probability independently from the rest of its row.

For a schema `0.5.0` transition derived from constant competing rates, do not use these probability-row targets. Uncertainty schemas `0.3.0` through `0.6.0` may instead target an exact positive event `rate_per_year` inside `input_provenance`; the uncertainty engine then recomputes the complete affected matrix or schedule before model validation. Gamma, lognormal, and strictly positive uniform rate distributions are admitted. Schemas `0.4.0` through `0.6.0` additionally admit evidence-bound Cholesky correlation only among lognormal scalar members. For a schema `0.6.0` survival transformation, uncertainty schema `0.5.0` or `0.6.0` may target only the exact positive exponential rate or Weibull shape or scale value and must recompute the complete schedule. For a schema `0.7.0` probability-time transformation, uncertainty schema `0.6.0` may target only its exact source probability with Beta or bounded Uniform and must recompute the complete transition input. General CTMC intensity uncertainty, arbitrary or unsupported correlated distributions, curve selection, and transformation-space structural scenarios remain unsupported.

## Explicit exclusions

The current first-party engine does not implement tunnel states automatically, time-since-entry transitions, patient-level history, recurrent-event trackers, general continuous-time matrix exponentiation, competing-probability conversion, relative-effect application, treatment-effect extrapolation formulas, dynamic populations, interactions, time-varying rewards, partitioned survival, or microsimulation. Only the separately admitted constant competing-rate, bounded two-state survival-curve, and single-event probability-time adapters are executable. They do not fit or select curves, reconstruct covariance, validate extrapolation or clinical applicability, combine competing events, or infer time-varying hazards. Record everything else as a structural gap; never approximate it invisibly with a model-cycle schedule.
