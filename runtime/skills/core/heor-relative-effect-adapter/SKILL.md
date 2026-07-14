---
name: heor-relative-effect-adapter
description: Derive, propagate bounded uncertainty through, and audit AI4HEOR analysis schema 0.10.0 two-state transition schedules from cycle-specific baseline event probabilities plus one aligned risk ratio or odds ratio. Use only for one absorbing event, an effect interval equal to the model cycle, exact baseline/effect provenance, and explicit endpoint, population, and constant-effect review bases; route hazard ratios to a future hazard-ratio adapter and stop for rate ratios, risk differences, competing events, effect waning, or clinical-validity claims.
---

# HEOR Relative Effect Adapter

Apply one evidence-bound RR or OR to cycle-specific baseline absolute risks and emit a complete two-state schedule. Read `references/relative-effect-contract.md` before changing an analysis or uncertainty plan.

## Workflow

1. Confirm exactly two states, one absorbing event state, 1–10,000 cycles, and one baseline event probability for every model cycle.
2. Confirm that the baseline risks, relative effect, endpoint, estimand, population, comparator, and follow-up interval are aligned. Keep `endpoint_alignment`, `population_transportability`, and `effect_constancy_over_cycles` as evidence or proposed-assumption bases, never approval fields.
3. Use analysis schema `0.10.0`, `derivation.method = "deterministic_transformation"`, `operation = "relative_effect_to_transition_schedule"`, and the exact transformation contract. Require `effect_interval_years` and `cycle_length_years` to equal the positive analysis cycle length.
4. Bind every baseline probability and the RR or OR value to exactly one selected extraction or one `proposed` assumption. Require at least one positive baseline probability.
5. For RR, compute `p_t = p_b * RR`; reject any non-finite result or result outside `[0,1)`. For OR, compute `p_t = OR*p_b / (1-p_b+OR*p_b)` with finite arithmetic and the same output bounds. Preserve the event state as absorbing and write every complete matrix to both the strategy schedule and `derivation.model_value`.
6. Run `scripts/validate_relative_effect.py`, `$heor-input-provenance`, browser/native review, and the deterministic engine. Treat structural validity as readiness for Human-in-the-loop review, not scientific approval.
7. For uncertainty, pair analysis `0.10.0` with uncertainty `0.9.0` and target only `relative_effect.value`. RR permits only bounded Uniform PSA and requires DSA/PSA high bounds strictly below `1 / max(positive baseline probability)`. OR permits Lognormal or strictly positive bounded Uniform PSA. Bind exactly the effect basis and retain at least one external structural scenario.
8. Report the measure, baseline risks, effect interval, exact bases, represented uncertainty, review bases, unsupported cases, and next human gate.

## Stop rules

- Do not interpret a hazard ratio, rate ratio, odds ratio, risk ratio, or risk difference as another measure. Route HR to a future `$heor-hazard-ratio-adapter`; the current survival Skill evaluates absolute curves and does not apply treatment effects.
- Do not convert probability time units inside this operation. Route an absolute single-event probability conversion to `$heor-probability-time-adapter`; stop if composed effect application and time conversion are required.
- Do not apply relative effects to competing events, composite or recurrent endpoints, multiple origin states, non-absorbing events, or partitioned-survival structures.
- Do not infer proportionality, effect constancy, population transportability, endpoint compatibility, or extrapolation beyond supported follow-up.
- Do not admit an all-zero baseline, an RR range or draw that can produce probability 1 or greater, an unbounded RR distribution, or independent mutation of derived probabilities.
- Do not pool studies, select an estimand, fit a model, create approval, claim independent validation, or give reimbursement or policy advice.

## Resources

- `references/relative-effect-contract.md`: exact fields, formulas, provenance, uncertainty, method basis, and stopping rules.
- `assets/relative-effect-transformation.template.json`: copyable three-cycle RR example.
- `scripts/validate_relative_effect.py`: standalone deterministic recomputation and optional expected-schedule comparison.
