---
name: heor-background-mortality
description: Derive and audit AI4HEOR schema 0.9.0 two-state transition schedules from age-aligned annual general-population mortality probabilities plus one constant additive excess mortality rate. Use when a selected life table and separately evidenced disease excess hazard must be combined without double counting, with exact provenance and Human-in-the-loop review boundaries.
---

# HEOR Background Mortality

Convert one selected life table plus one constant additive disease excess mortality rate into a complete, reviewable two-state schedule. Read `references/background-mortality-contract.md` before changing a plan.

## Workflow

1. Confirm the bounded case: exactly two states, one absorbing death state, 1–10,000 cycles, and a finite positive cycle length.
2. Stop if the supplied endpoint is already all-cause; cause-specific and subdistribution quantities are mixed; calendar mortality improvement, age/sex mixtures, time-varying excess hazards, competing non-death events, or partitioned survival are required.
3. Use analysis schema `0.9.0`, `derivation.method = "deterministic_transformation"`, the exact operation `background_plus_excess_mortality_to_transition_schedule`, and a complete `strategies.<strategy_id>.transition_schedule` mapping.
4. Declare `life_table` with jurisdiction, table year, population, sex, start age, and exactly one annual-probability record per model cycle. Set `attained_age_years = floor(start_age_years + (cycle - 1) * cycle_length_years)`.
5. Bind every `annual_probability` and `excess_mortality_rate_per_year` value to exactly one selected extraction or proposed assumption. Keep `population_exchangeability` and `no_double_counting` as exact evidence/assumption bases; they are not approval fields.
6. Recompute each cycle as `h_bg = -ln(1-q_annual)`, `h_total = h_bg + h_excess`, and `p_death = 1-exp(-h_total * cycle_length_years)`. Never multiply an annual probability directly by cycle length.
7. For uncertainty, pair analysis `0.9.0` with uncertainty `0.8.0`. Parameter targets may vary only the exact positive `excess_mortality_rate_per_year.value`; keep the life table and review bases fixed. Retain at least one ordinary allowlisted structural scenario, but never mutate transformation internals.
8. Record additive-versus-multiplicative mortality as a structural limitation. ISPOR-SMDM notes that the functional form can materially change results; this version does not implement SMR or other multiplicative structures.
9. Run `scripts/validate_background_mortality.py`, then `$heor-input-provenance` and `$heor-uncertainty-analysis` when applicable. Treat structural validity as readiness for app-owned human review, not scientific approval.

## Boundaries

- Do not choose a life table, assert population exchangeability, infer sex or age mixtures, or decide that double counting is absent.
- Do not fit survival curves, apply treatment effects, derive excess mortality from an all-cause endpoint, or introduce competing events.
- Do not add `approved`, `status`, or rationale-as-approval fields to `review_bases`.
- Do not claim clinical validity, independent validation, reimbursement suitability, or policy advice.

## Resources

- `references/background-mortality-contract.md`: exact fields, formula, provenance, uncertainty, evidence basis, and stopping rules.
- `assets/background-mortality-transformation.template.json`: half-year-cycle example with attained-age alignment.
- `scripts/validate_background_mortality.py`: standalone deterministic recomputation and optional expected-schedule comparison.
