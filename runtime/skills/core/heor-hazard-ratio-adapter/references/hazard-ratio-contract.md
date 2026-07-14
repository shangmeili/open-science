# Hazard-ratio transformation contract

## Scope

This contract turns one already-selected baseline cumulative-hazard curve and
one constant hazard ratio into a complete two-state transition schedule. It is
a deterministic representation step, not a survival-analysis or causal-validity
decision.

## Exact transformation

Use only these root fields: `operation`, `cycle_length_years`,
`from_state_index`, `event_state_index`, `baseline_cumulative_hazards`,
`hazard_ratio`, and `review_bases`. The operation is
`hazard_ratio_to_transition_schedule`; cycle length is positive and equals the
analysis cycle; the indices are the two distinct states.

Each baseline entry has exact fields `cycle` and `cumulative_hazard`. Cycles are
one-based and contiguous. Each cumulative hazard is finite, non-negative,
non-decreasing, and bound to exactly one extraction or proposed assumption.

For cycle `i`, with `H0(0)=0`:

`delta_H0(i) = H0(i) - H0(i-1)`

`p(i) = 1 - exp(-HR * delta_H0(i)) = -expm1(-HR * delta_H0(i))`

The event state remains absorbing. At least one hazard increment is positive.
Every output probability is finite and in `[0,1)`.

## Required review bases

- `endpoint_alignment`
- `population_transportability`
- `proportional_hazards_assumption`
- `effect_constancy_over_horizon`
- `treatment_switching_assessment`

Each declares exactly one selected extraction or one proposed assumption. These
fields record why the transformation was proposed; they never record approval.

## Uncertainty

Pair analysis schema `0.11.0` only with uncertainty schema `0.10.0`. Vary only
`/input_provenance/{mapping}/derivation/transformation/hazard_ratio/value`.
The DSA interval brackets the positive base HR. PSA uses a strictly positive
bounded Uniform because an unbounded distribution cannot guarantee a
numerically valid probability for every draw. Both high bounds must reproduce a
valid schedule. Bind exactly the HR basis. Baseline hazards, review bases,
indices, and schedule structure remain fixed.

## Method basis

NICE PMG36 section 4.6 requires proportional hazards to be assessed and allows
pooling HRs only when proportional hazards holds in-trial and remains clinically
plausible during extrapolation. NICE DSU TSD14 describes applying an HR to a
base survival curve only under proportional hazards and requires treatment-
effect duration and HR provenance to be justified. NICE DSU TSD21 is the route
for non-proportional hazards and flexible survival methods.

Primary sources:

- [NICE PMG36, economic evaluation, section 4.6](https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2/)
- [NICE DSU TSD14, survival analysis for economic evaluations](https://www.sheffield.ac.uk/sites/default/files/2022-02/TSD14-Survival-analysis.updated-March-2013.v2.pdf)
- [NICE DSU TSD21, flexible methods for survival analysis](https://www.sheffield.ac.uk/sites/default/files/2022-02/TSD21-Flex-Surv-TSD-21_Final_alt_text.pdf)

## Unsupported

Stop for time-varying HRs, waning or stopping effects, unresolved treatment
switching, competing or recurrent events, curve fitting or selection, evidence
synthesis, partitioned survival, or scientific-validity claims.
