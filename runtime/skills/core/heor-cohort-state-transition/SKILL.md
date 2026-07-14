---
name: heor-cohort-state-transition
description: Build, audit, and explain AI4HEOR deterministic cohort state-transition models with static or piecewise model-cycle-dependent transition matrices. Use when translating an approved conceptual model into heor/analysis-plan.json, representing treatment waning or other transition changes over model time, checking matrix and cycle semantics, preparing uncertainty targets, or deciding that time-in-state, patient history, interactions, or heterogeneity require a different model type.
---

# HEOR Cohort State Transition

Build the smallest adequate executable cohort model from the current project artifacts. Read `references/model-contract.md` before creating or changing transition inputs.

## Workflow

1. Read the current decision problem, `heor/conceptual-model.json`, `heor/evidence-synthesis.json`, and `heor/analysis-plan.json`. Never infer that a workspace artifact is approved.
2. Confirm that a closed cohort with mutually exclusive, collectively exhaustive states is adequate. Stop if interactions, continuous patient attributes, event history, or time in state materially determine outcomes and cannot be represented with a manageable state set.
3. Use one static `transition_matrix` per strategy when probabilities do not change over model cycle. Use a `transition_schedule` only when evidence or an explicit proposed assumption supports model-cycle-dependent matrices. Use schema `0.8.0` for ordinary multi-strategy analysis, `0.9.0` only for background mortality, and `0.10.0` only for the admitted RR/OR relative-effect transformation. Preserve schemas `0.4.0`–`0.7.0` for compatible legacy projects.
4. Define exactly one transition mechanism per strategy. For a schedule, start at cycle 1, add only strictly increasing change points within the horizon, and provide a complete square probability matrix at every phase.
5. Preserve the distinction between model time and time in state. A schedule changes all cohort members at a model cycle; it does not create tunnel-state or semi-Markov memory.
6. Map the complete static matrix or schedule through `$heor-input-provenance`. Use the rate, survival, probability-time, and background-mortality Skills only for their existing absolute-input contracts. Use `$heor-relative-effect-adapter` only for one absorbing event with cycle-specific baseline risks and one aligned RR or OR. Route HR to a future `$heor-hazard-ratio-adapter`; do not apply HR to probabilities, coerce effect measures, combine competing events, or extrapolate treatment effects through prose.
7. Use `$heor-uncertainty-analysis` for evidence-supported uncertainty. Pair analysis/uncertainty `0.8.0`/`0.7.0`, background mortality `0.9.0`/`0.8.0`, and relative effect `0.10.0`/`0.9.0`. Relative-effect uncertainty varies only the effect value; RR is bounded below the risk-valid ceiling and OR is positive. Never vary the derived transition rows independently.
8. Run the deterministic engine through the review panel, inspect cohort mass in every cycle, transition mode and change points, disaggregated strategy results, and exact input hash. Treat output as calculation-only.
9. Report why the cohort form is adequate, static versus scheduled strategies, every change point and evidence basis, unsupported history dependence, uncertainty coverage, and the next Human-in-the-loop gate.

## Boundaries

- Never invent a transition probability or silently infer a treatment-waning profile.
- Stop the background-mortality route when the supplied endpoint is already all-cause, cause-specific and subdistribution quantities are mixed, calendar mortality improvement or age/sex mixtures must be modeled, excess mortality varies over time, competing non-death events exist, or the structure is partitioned survival.
- Never label a model-cycle schedule as time-in-state, tunnel-state, semi-Markov, or individual simulation. Legacy schemas `0.6.0` and `0.7.0`, or schema `0.8.0` at a declared strategy path, may respectively evaluate an admitted survival curve or convert a declared source probability under constant hazard; neither establishes clinical validity.
- Do not use a schedule to hide state explosion or material heterogeneity.
- Keep time-varying costs and utilities explicit as unsupported; this engine varies transition matrices only.
- Do not create approval, evidence-review, validation, release, reimbursement, or policy claims.
