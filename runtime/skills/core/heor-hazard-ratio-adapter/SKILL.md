---
name: heor-hazard-ratio-adapter
description: Derive, propagate bounded uncertainty through, and audit AI4HEOR analysis schema 0.11.0 two-state transition schedules from cycle-aligned baseline cumulative hazards plus one reviewed constant hazard ratio. Use only for one absorbing time-to-first event under explicit proportional-hazards, endpoint, population, treatment-effect-duration, and treatment-switching review bases; stop for time-varying HRs, effect waning, competing or recurrent events, curve fitting, partitioned survival, or clinical-validity claims.
---

# HEOR Hazard Ratio Adapter

Apply one evidence-bound constant HR to cycle-specific increments of a selected
baseline cumulative-hazard curve. Read `references/hazard-ratio-contract.md`
before changing an analysis or uncertainty plan.

## Workflow

1. Confirm exactly two states, one absorbing time-to-first-event state, 1–10,000 cycles, and one cumulative baseline hazard at the end of every model cycle.
2. Confirm the baseline curve and HR share the endpoint, estimand, population, comparator, and time origin. Keep all five `review_bases` as evidence or proposed-assumption bases, never approval fields.
3. Use analysis schema `0.11.0`, `derivation.method = "deterministic_transformation"`, `operation = "hazard_ratio_to_transition_schedule"`, and the exact transformation contract.
4. Bind every cumulative hazard and the HR to exactly one selected extraction or one `proposed` assumption. Require non-negative, non-decreasing cumulative hazards and at least one positive increment.
5. For cycle `i`, compute `delta_H0 = H0(i) - H0(i-1)`, with `H0(0)=0`, then `p_i = -expm1(-HR * delta_H0)`. Reject non-finite arithmetic or any probability outside `[0,1)`. Preserve the event state as absorbing and write the complete schedule to both the strategy and `derivation.model_value`.
6. Run `scripts/validate_hazard_ratio.py`, `$heor-input-provenance`, browser/native review, and the deterministic engine. Structural validity is readiness for human review, not scientific approval.
7. For uncertainty, pair analysis `0.11.0` with uncertainty `0.10.0` and target only `hazard_ratio.value`. Use a strictly positive bounded Uniform PSA distribution whose DSA and PSA highs can reproduce a valid complete schedule. Keep the baseline hazards and transformation structure fixed and retain at least one external structural scenario.
8. Report the HR, baseline cumulative hazards, exact bases, represented uncertainty, unsupported cases, and next human gate.

## Stop rules

- Do not multiply a cycle probability by an HR. Route RR or OR to `$heor-relative-effect-adapter`; never substitute one effect measure for another.
- Stop if proportional hazards are not supported within observed follow-up or are not clinically plausible across the modeled horizon. Route time-varying effects and non-proportional hazards to a future flexible-survival method.
- Stop when treatment effect stops, wanes, changes after discontinuation, or needs multiple scenarios inside the transformation.
- Do not apply this operation to competing, composite, recurrent, cause-specific versus subdistribution-mismatched, multiple-origin, or non-absorbing events.
- Do not use an HR affected by unresolved treatment switching, an HR from an incompatible model, or a baseline curve from a different estimand or time origin.
- Do not fit or select survival curves, pool HRs, reconstruct individual patient data, infer transportability, create approval, claim independent validation, or give reimbursement or policy advice.

## Resources

- `references/hazard-ratio-contract.md`: exact fields, formula, provenance, uncertainty, method basis, and stopping rules.
- `assets/hazard-ratio-transformation.template.json`: copyable three-cycle example.
- `scripts/validate_hazard_ratio.py`: standalone deterministic recomputation and optional expected-schedule comparison.
