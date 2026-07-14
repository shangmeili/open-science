---
name: heor-survival-curve-adapter
description: Derive, propagate bounded parameter uncertainty through, and audit AI4HEOR schema 0.6.0 two-state model-cycle transition schedules from already-selected exponential or Weibull survival curves. Use when an all-cause time-to-event endpoint has positive, auditable parameters and must become a complete cohort schedule or evidence-bound DSA/PSA; do not use to fit or select curves, reconstruct IPD, combine PFS and OS, apply relative effects, model competing risks, or claim extrapolation validity.
---

# HEOR Survival Curve Adapter

Convert one declared all-cause survival curve into a complete, deterministic two-state transition schedule. Read `references/survival-curve-contract.md` before changing an analysis plan.

## Workflow

1. Read the decision problem, conceptual model, evidence synthesis, analysis plan, and input provenance. Confirm the endpoint and both state meanings in natural language before editing JSON.
2. Confirm the bounded case: exactly two states, one origin state, one absorbing all-cause event state, 1–10,000 model cycles, and one already-selected exponential or Weibull curve. Stop if fitting, curve selection, competing risks, PFS/OS consistency, treatment-effect application, or individual history is required. Route a selected life table plus a separate constant additive excess mortality rate to `$heor-background-mortality` instead.
3. Bind every positive curve parameter to exactly one selected strict-JSON extraction or one `proposed` assumption. Never infer a missing scale convention or translate another parameterization silently.
4. Use analysis schema `0.6.0`. Map only `strategies.<role>.transition_schedule`; set `derivation.method = "deterministic_transformation"` and `operation = "parametric_survival_to_transition_schedule"`.
5. Recompute every model-cycle probability from the cumulative-hazard increment in the reference contract. Emit one complete matrix per cycle, beginning at cycle 1. Preserve the absorbing event state.
6. Require the recomputed output to equal both `derivation.model_value` and the current schedule. Require exact equality between mapping-level extraction and assumption IDs and the bases actually used by the parameters.
7. When evidence supports parameter uncertainty, use current `$heor-uncertainty-analysis` schema `0.6.0` (`0.5.0` remains readable). Target only the exact parameter `value` under the indexed transformation, use positive DSA bounds and gamma, lognormal, or strictly positive uniform PSA values, and bind exactly that parameter's extraction or proposed assumption. Let the engine recompute the complete schedule after all replacements. Keep alternative curve families as separately reviewed structural uncertainty.
8. Run `scripts/validate_survival_curve.py` on the transformation and expected schedule, then run `$heor-input-provenance`, `$heor-uncertainty-analysis` when applicable, and the deterministic HEOR engine. Inspect cycle count, schedule starts, row sums, cohort-mass conservation, parameter-draw recomputation, and the exact evidence hash.
9. Report the distribution and parameterization, basis for every parameter, time unit, observed-data boundary if known, generated schedule, represented and omitted uncertainty, unsupported methods, unresolved extrapolation questions, and the next Human-in-the-loop review gate.

## Boundaries

- This adapter evaluates declared parameters; it does not fit data, compare statistical fit, select a distribution, reconstruct patient-level data, or establish internal or external validity.
- Exponential uses `rate_per_year`; Weibull uses the scale-in-years and shape form in the contract. Do not substitute another Weibull convention.
- Uncertainty schema `0.5.0` or `0.6.0` admits only exact positive exponential or Weibull parameter values. It does not fit covariance, infer distributions from confidence intervals, choose curves, or validate extrapolation. Never vary derived probabilities independently.
- Do not describe this as partitioned survival, competing-risk, semi-Markov, cure, mixture, spline, or background-mortality modeling.
- Do not create or claim evidence verification, human approval, independent model validation, reimbursement, or policy advice.

## Resources

- `references/survival-curve-contract.md`: exact formulas, provenance shape, method basis, and exclusions.
- `assets/survival-transformation.template.json`: copyable transformation declaration.
- `scripts/validate_survival_curve.py`: standalone deterministic recomputation and optional expected-schedule comparison.
