---
name: heor-transition-rate-adapter
description: Derive, propagate uncertainty through, and audit AI4HEOR schema 0.5.0 cohort transition matrices or model-cycle schedules from constant cause-specific competing event rates. Use when evidence reports rates rather than cycle probabilities, each event can be bound to one extraction or proposed assumption, or current uncertainty schema 0.6.0 needs rate-space DSA/PSA and an evidence-bound lognormal correlation group; do not use for probability time conversion, relative effects, general CTMCs, extrapolation, or arbitrary correlated-rate models.
---

# HEOR Transition Rate Adapter

Convert a narrow, reviewable class of event-rate evidence into deterministic cohort transition inputs. Read `references/transition-rate-contract.md` before changing an analysis plan.

## Workflow

1. Read the decision problem, conceptual model, evidence synthesis, analysis plan, and current input provenance. Never treat an external asset or agent output as approved evidence.
2. Confirm the bounded case: rates are positive, constant within each declared phase, cause-specific, mutually exclusive first events from one state, and use the exact model-cycle duration. Stop if multiple within-cycle state changes or a general continuous-time transition system matter.
3. Bind every nonzero event rate to exactly one selected extraction or one `proposed` assumption. Preserve structural zeros by omitting events; represent an absorbing row with an empty event list.
4. Use schema `0.5.0` and a transition-path provenance mapping with `derivation.method = "deterministic_transformation"`, `operation = "constant_competing_rates"`, and a complete ordered row declaration for every phase.
5. Recompute each row using the contract formula. Use one phase for a static matrix. For a schedule, start at cycle 1, use strictly increasing model-cycle change points, and derive every complete matrix.
6. Require the derived output to equal both `derivation.model_value` and the current transition matrix or schedule. Require the transformation to use every declared extraction and assumption ID exactly.
7. When evidence supports rate uncertainty, use current `$heor-uncertainty-analysis` schema `0.6.0` (schemas `0.3.0` through `0.5.0` remain readable). Target only the exact event `rate_per_year`, require positive DSA bounds and gamma, lognormal, or strictly positive uniform PSA values, and bind the sole basis ID to that event. Let the engine recompute the affected complete transition input after all rate replacements in each run. Only evidence-supported lognormal rate members may share a bounded Cholesky correlation group; preserve every other known rate dependence as a review blocker.
8. Run `$heor-input-provenance` validation and the deterministic HEOR engine. For rate-space uncertainty, also run the uncertainty validator and inspect seeded DSA/PSA results. Inspect row sums, cohort-mass conservation, transition mode, change points, and exact input hashes.
9. Report the rate basis, cycle length, formula, phase boundaries, resulting matrices, sampled versus fixed rates, unsupported transformations, dependence assumptions, and the next Human-in-the-loop review gate.

## Boundaries

- Do not convert probabilities between time units, apply HR/RR/OR values, pool studies, calibrate, or extrapolate effects with this adapter. Route aligned cycle-specific risks plus RR/OR to `$heor-relative-effect-adapter`; route one reviewed constant HR plus cycle-aligned baseline cumulative hazards to `$heor-hazard-ratio-adapter`; leave rate ratios incomplete for a future rate-relative-effect contract.
- Do not call this a general CTMC or matrix-exponential solution. It assumes at most one state change within a model cycle.
- Do not vary a derived probability row while leaving its rate transformation unchanged. Use only the admitted event-rate target so the engine recomputes the full transformation. Only the evidence-bound lognormal Cholesky group is implemented for dependence; arbitrary correlated-rate models and transformation-space structural scenarios remain unsupported.
- Do not create or claim evidence verification, human approval, model validation, reimbursement, or policy advice.
