---
name: heor-cohort-state-transition
description: Build, audit, and explain AI4HEOR deterministic cohort state-transition models with static or piecewise model-cycle-dependent transition matrices. Use when translating an approved conceptual model into heor/analysis-plan.json, representing treatment waning or other transition changes over model time, checking matrix and cycle semantics, preparing uncertainty targets, or deciding that time-in-state, patient history, interactions, or heterogeneity require a different model type.
---

# HEOR Cohort State Transition

Build the smallest adequate executable cohort model from the current project artifacts. Read `references/model-contract.md` before creating or changing transition inputs.

## Workflow

1. Read the current decision problem, `heor/conceptual-model.json`, `heor/evidence-synthesis.json`, and `heor/analysis-plan.json`. Never infer that a workspace artifact is approved.
2. Confirm that a closed cohort with mutually exclusive, collectively exhaustive states is adequate. Stop if interactions, continuous patient attributes, event history, or time in state materially determine outcomes and cannot be represented with a manageable state set.
3. Use one static `transition_matrix` per strategy when probabilities do not change over model cycle. Use a `transition_schedule` only when evidence or an explicit proposed assumption supports model-cycle-dependent matrices; use schema `0.5.0` when `$heor-transition-rate-adapter` derives transitions, schema `0.6.0` when `$heor-survival-curve-adapter` derives the admitted two-state schedule, and otherwise use `0.4.0`.
4. Define exactly one transition mechanism per strategy. For a schedule, start at cycle 1, add only strictly increasing change points within the horizon, and provide a complete square probability matrix at every phase.
5. Preserve the distinction between model time and time in state. A schedule changes all cohort members at a model cycle; it does not create tunnel-state or semi-Markov memory.
6. Map the complete static matrix or schedule through `$heor-input-provenance`. Use `$heor-transition-rate-adapter` only for bounded constant competing rates and `$heor-survival-curve-adapter` only for its already-selected two-state exponential or Weibull case. Do not assemble probabilities, perform other rate or hazard conversions, pool sources, fit or select curves, extrapolate treatment effects, or normalize competing risks through prose; leave unsupported derivations incomplete.
7. Use `$heor-uncertainty-analysis` for evidence-supported uncertainty. Sample a directly modeled complete probability row with Dirichlet. For analysis schema `0.5.0` rate-derived transitions, vary only exact positive event-rate targets; for analysis schema `0.6.0` survival schedules, use uncertainty schema `0.5.0` and vary only exact positive curve-parameter values. The engine must recompute the complete affected transformation. Correlate only evidence-bound lognormal members through the bounded Cholesky contract. Test directly declared schedule change points only as structural scenarios.
8. Run the deterministic engine through the review panel, inspect cohort mass in every cycle, transition mode and change points, disaggregated strategy results, and exact input hash. Treat output as calculation-only.
9. Report why the cohort form is adequate, static versus scheduled strategies, every change point and evidence basis, unsupported history dependence, uncertainty coverage, and the next Human-in-the-loop gate.

## Boundaries

- Never invent a transition probability or silently infer a treatment-waning profile.
- Never label a model-cycle schedule as time-in-state, tunnel-state, semi-Markov, or individual simulation. A schema `0.6.0` schedule may evaluate a declared survival curve, but it does not establish fit or extrapolation validity.
- Do not use a schedule to hide state explosion or material heterogeneity.
- Keep time-varying costs and utilities explicit as unsupported; this engine varies transition matrices only.
- Do not create approval, evidence-review, validation, release, reimbursement, or policy claims.
