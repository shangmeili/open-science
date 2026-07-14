---
name: heor-probability-time-adapter
description: Convert, propagate bounded uncertainty through, and audit AI4HEOR schema 0.7.0 single-event probabilities from a declared source interval to the model cycle under an explicit constant-hazard assumption. Use when one state row has zero or one event, a probability strictly between 0 and 1 has an auditable time interval and evidence or proposed-assumption basis, and the complete transition matrix or schedule must be deterministically recomputed; do not use for competing events, probability 0 or 1, time-varying hazards, HR/RR/OR application, composite endpoints, pooling, or clinical-validity claims.
---

# HEOR probability time adapter

Convert one bounded event probability to the model cycle without dividing the
probability by the number of cycles. Read `references/probability-time-contract.md`
before changing an analysis or uncertainty plan.

## Workflow

1. Confirm that each affected state row has zero or one outbound event. Stop for competing events.
2. Record the source probability, source interval in years, model-cycle length, target state, and constant-hazard rationale.
3. Bind the probability to exactly one strict-JSON extraction or one `proposed` assumption. Preserve the optional JSON pointer.
4. Use analysis schema `0.7.0`, `derivation.method = "deterministic_transformation"`, and `operation = "single_event_probability_time_conversion"`.
5. Compute `1 - exp(log(1-p) * cycle_length / source_interval)` and write the complete matrix or schedule to both the model input and `derivation.model_value`.
6. Run `scripts/validate_probability_time.py`, `$heor-input-provenance`, the browser preview, native review, and the deterministic HEOR engine.
7. When evidence supports uncertainty, use `$heor-uncertainty-analysis` schema `0.6.0`. Target only the exact `source_probability`, use Beta or Uniform strictly inside `(0,1)`, and let every run recompute the complete transition input.
8. Report the constant-hazard assumption, input interval, output cycle, evidence basis, unsupported cases, and next Human-in-the-loop gate.

## Stop rules

- Do not convert by simple division or multiplication.
- Do not combine two or more event probabilities in one row.
- Do not admit source probability `0` or `1`; represent a structural zero with `event: null` and review certain events separately.
- Do not infer constancy, independence, a relative effect, source interval, or clinical applicability.
- Do not mutate a derived probability row in DSA or PSA.
- Do not claim evidence verification, model validation, approval, reimbursement, or policy advice.

## Resources

- `references/probability-time-contract.md`: formula, schema, method basis, and exclusions.
- `assets/probability-time-transformation.template.json`: copyable transformation declaration.
- `scripts/validate_probability_time.py`: standalone deterministic recomputation.
