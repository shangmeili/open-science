# Cohort state-transition model contract

## Selection boundary

Use a cohort state-transition model when the decision problem can be represented by a closed cohort, a manageable set of mutually exclusive and collectively exhaustive states, and no interaction between people. Relevant history must either be unnecessary or represented transparently in the state structure. If time in state, prior events, continuously varying patient attributes, dynamic treatment rules, or interactions materially determine transitions or rewards, this bounded engine is not an adequate substitute for a semi-Markov, individual-level, discrete-event, or dynamic model.

Method basis:

- [ISPOR-SMDM state-transition good practices](https://www.ispor.org/publications/journals/value-in-health/abstract/Volume-15--Issue-6/State-Transition-Modeling--A-Report-of-the-ISPOR-SMDM-Modeling-Good-Research-Practices-Task-Force-3) recommends choosing cohort simulation only when relevant characteristics and histories can be represented with manageable states. It identifies time-dependent parameters as a reason to use a state-transition approach.
- [NICE PMG36 economic evaluation](https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2) requires transparent, decision-problem-specific model structure, documented inputs, appropriate time horizon, alternative extrapolation scenarios, uncertainty analysis, and validation.

These sources support the review questions; they do not certify an AI4HEOR model.

## Executable transition contract

Analysis schema `0.4.0` accepts exactly one transition mechanism for each strategy:

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
- Schema `0.3.0` remains valid for static matrices. Schedules require `0.4.0`; older schemas must reject them.

The result records `transition_mode` as `static` or `piecewise_by_model_cycle` and reports the effective schedule start cycles. The exact input bytes remain the authoritative record of matrices.

## Evidence and uncertainty

Map a static matrix at `strategies.<role>.transition_matrix`. Map a schedule at `strategies.<role>.transition_schedule`. The derivation snapshot must equal the complete current value. A direct-evidence extraction must contain strict JSON equal to that complete matrix or schedule; unsupported assembly from several estimates remains incomplete.

Allowed uncertainty row targets are:

```text
/strategies/<role>/transition_matrix/<row>
/strategies/<role>/transition_schedule/<phase>/matrix/<row>
```

Use a coherent complete simplex for deterministic bounds and a Dirichlet distribution for PSA. A structural scenario may change an allowlisted schedule `start_cycle`; the resulting complete model must still pass ordering and horizon validation. Do not vary one probability independently from the rest of its row.

## Explicit exclusions

The current first-party engine does not implement tunnel states automatically, time-since-entry transitions, patient-level history, recurrent-event trackers, continuous-time hazards, rate-to-probability or hazard-to-competing-risk conversion, treatment-effect extrapolation formulas, dynamic populations, interactions, time-varying rewards, partitioned survival, or microsimulation. Record these as structural gaps or use a separately admitted deterministic adapter; never approximate them invisibly with a model-cycle schedule.
