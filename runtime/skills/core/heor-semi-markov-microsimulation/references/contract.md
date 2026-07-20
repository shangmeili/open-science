# Bounded individual state-transition contract 0.1.0

## Selection boundary

Use this model only when the decision problem remains a closed, non-interacting cohort but time in the current state or prior events materially determine transitions or rewards and transparent cohort-state expansion is unmanageable. The Human researcher must justify that choice for the current decision problem.

The contract follows the distinction in the [ISPOR-SMDM state-transition task-force report](https://pubmed.ncbi.nlm.nih.gov/22999130/): individual-level models retain tracker variables and use first-order Monte Carlo draws, while sufficient simulated individuals and variance assessment are needed for stable estimates. [NICE PMG36](https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2/) requires model type and structure to be justified, inputs documented, quality assurance and validation reported, and outputs disaggregated. These sources guide review; they do not certify any AI4HEOR result.

## Exact execution semantics

- A patient occupies exactly one of 2–8 ordered states at every cycle boundary. Exactly one state is an absorbing death state.
- Each state has zero or more non-overlapping conditional rules followed by exactly one `otherwise` rule. A condition may use completed cycles in the current state and 1–3 capped event-entry tracker counts. The selected rule supplies the complete transition row, annual state cost, and utility.
- One transition occurs at each cycle end. Event trackers update after that transition. A changed state starts with zero completed cycles; remaining in the same state increments completed cycles by one.
- State cost, QALY, and life-year rewards use a fixed trapezoidal boundary convention. Transition-event costs occur at the cycle end. Costs and outcomes use their separately declared annual discount rates.
- SplitMix64 counter output converted from its top 53 bits supplies one initialization uniform and one transition uniform per patient-cycle. The same `(seed, replicate, patient, cycle, stream)` counter is used for every strategy, providing common random numbers without path-dependent stream shifts.
- The first strategy is the baseline. Strategy differences are paired by replicate and patient. Arithmetic ICER/dominance patterns and net monetary benefit are descriptive; no automatic strategy-selection threshold exists.
- Three to twenty independent counter replicates and at least 100 patients per replicate are required. Patient-level standard errors and between-replicate variation are both reported. The full calculation is capped at 5,000,000 patient-strategy-cycles and portable audit reruns every step.
- Only prespecified patient indices from one prespecified replicate enter `traces.jsonl`. The trace binds state, time in state, tracker counts, rule, uniforms, rewards, and cumulative outcomes.

## Excluded from schema 0.1.0

- interactions, infectious-disease transmission, queues, capacity constraints, or shared resources;
- open or replenished populations, competing simultaneous events, or continuous-time discrete-event simulation;
- continuous or changing patient covariates, risk equations, dynamic treatment policies, adherence or treatment switching logic;
- automatic state, tracker, rule, strategy, parameter, seed, sample-size, or stability-threshold selection;
- parameter uncertainty, probabilistic sensitivity analysis, calibration, value-of-information analysis, or structural averaging;
- claims of clinical validity, causal validity, cost effectiveness, reimbursement, or policy authority;
- automatic replacement of an analysis plan, economic-model input, or released result.
