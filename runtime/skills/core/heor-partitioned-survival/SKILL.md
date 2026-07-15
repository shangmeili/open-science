---
name: heor-partitioned-survival
description: Create, repair, or validate AI4HEOR three-state partitioned survival plans from aligned PFS and OS curve values. Use when an oncology or forward-only disease model needs progression-free, progressed, and dead occupancy; when PFS/OS extrapolations must be bound to reviewed curve artifacts; or when a partitioned survival calculation must fail closed on curve crossing, time-grid mismatch, or incoherent occupancy.
---

# HEOR Partitioned Survival

Create a deterministic, hash-bound `heor/partitioned-survival-plan.json` without representing partitioned survival as a Markov transition matrix.

## Workflow

1. Use `$heor-economic-inputs` to create or validate the structure-neutral `heor/analysis-plan.json` schema `0.12.0`, then read the selected PFS and OS curve reviews and [references/contract.md](references/contract.md).
2. Confirm the decision process is forward-only and the analysis states are exactly `progression_free`, `progressed`, and `dead` in that order. Stop if this structure is not justified.
3. Confirm every strategy uses the same population, time origin, time unit, cycle grid, and horizon for PFS and OS. Preserve unresolved differences as blockers; do not normalize them silently.
4. Use `$heor-survival-curve-materialization` to create and validate `heor/survival-curve-materializations.json`. Stop if a curve is not an admitted exponential-rate or Weibull AFT shape/scale materialization.
5. Use `$heor-treatment-effect-duration` to state the evidence horizon and shared endpoint HR basis, create the sustained, immediate-stop, and log-linear-waning scenarios, and select one Human-reviewable base case. Stop instead of inferring duration from the HR point estimate.
6. Copy [assets/partitioned-survival-plan.template.json](assets/partitioned-survival-plan.template.json) to `heor/partitioned-survival-plan.json` and replace every placeholder.
7. Bind `base_analysis.content_sha256`, `curve_materializations.content_sha256`, and `treatment_effect_duration.content_sha256` to the exact current bytes. Bind each endpoint to the exact reviewed curve artifact, its logical target `partitioned_survival.strategies.<strategy_id>.<endpoint>`, and the Human-selected converged family.
8. Use the selected duration scenario's complete PFS and OS values in PSM schema `0.4.0`, preserving its exact duration-scenario basis IDs. Do not enter free-text or substitute basis IDs.
9. Calculate the implied checks without editing the duration-derived curves:
   - progression free = PFS
   - progressed = OS - PFS
   - dead = 1 - OS
10. Stop if PFS or OS increases, PFS exceeds OS, a time point is absent or duplicated, or state occupancy is negative or fails to sum to one.
11. Record the rationale for independent endpoint extrapolation, its limitations, and face, internal, and external validation tasks.
12. Set `status` to `ready_for_human_review` only after all placeholders and blockers are resolved.
13. Run both portable validators:

```bash
python3 runtime/skills/core/heor-partitioned-survival/scripts/validate_partitioned_survival.py \
  heor/analysis-plan.json heor/partitioned-survival-plan.json \
  heor/survival-curve-materializations.json \
  --treatment-effect-duration heor/treatment-effect-duration.json \
  --workspace-root .
python3 runtime/skills/core/heor-treatment-effect-duration/scripts/validate_treatment_effect_duration.py \
  heor/treatment-effect-duration.json heor/analysis-plan.json \
  heor/partitioned-survival-plan.json heor/survival-curve-materializations.json
```

## Boundaries

- Keep natural-language rationale and evidence IDs in the artifact; use forms only to assist exact value entry.
- Do not infer OS from PFS, PFS from OS, or transitions from state occupancy.
- Do not infer an evidence horizon, duration, or waning period from an HR point estimate; keep the source fit curves immutable and derive the intervention tail from comparator hazard increments.
- Do not clamp, reorder, smooth, splice, or otherwise repair curves unless a human-reviewed method and replacement artifact explicitly authorize the transformation.
- Do not describe this calculation as a Markov or state-transition model.
- Do not add an initial distribution, transition matrix, or transition schedule to satisfy another model's schema.
- Do not claim evidence verification, human approval, independent validation, cost effectiveness, reimbursement, or policy authority.
- Leave the artifact in `draft` and report exact blockers when the contract cannot be satisfied.

## Deliverable

Return the plan path, validator result, exact input hashes, any unresolved blockers, and the next required human review. Keep approval actions outside the Skill output.
