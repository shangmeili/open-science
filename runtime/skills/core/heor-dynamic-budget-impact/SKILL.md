---
name: heor-dynamic-budget-impact
description: Create, audit, and explain a hash-bound three-year dynamic annual-cohort payer budget impact plan with prevalent and incident populations, scenario-specific new-patient uptake and comparator displacement, treatment persistence and discontinuation, mortality, intervention-start capacity, itemized costs, sensitivity analyses, and alternative scenarios. Use when preparing or repairing schema 0.2.0 heor/budget-impact-plan.json, when population entry and exit make the static calculator unsuitable, or when the researcher asks how uptake, persistence, displacement, mortality, or capacity changes payer expenditure without requesting patient-level simulation.
---

# HEOR Dynamic Budget Impact

Build a transparent annual-boundary cohort calculation under researcher-defined assumptions. Read `references/dynamic-budget-impact-contract.md` before changing the artifact.

## Workflow

1. Read the exact current `heor/analysis-plan.json` bytes. Confirm its jurisdiction, canonical budget-impact path, and the two distinct declared strategy IDs selected for this BIA.
2. Explain why annual eligible totals are insufficient. If entry, exit, switching, persistence, mortality, or capacity is not material, use `$heor-budget-impact` schema `0.1.0` instead.
3. Copy `assets/dynamic-budget-impact-plan.template.json` to `heor/budget-impact-plan.json`; never mutate a previously released result file.
4. Record the initial prevalent treated population, each annual incident cohort, and the common annual mortality probabilities. Do not infer them from the cost-effectiveness cohort.
5. For each without/with-access scenario, record initial intervention share, incident intervention uptake, comparator displacement, and intervention-start capacity. Keep every intervention-flow input at zero in the without-access scenario.
6. Record comparator and intervention continuation probabilities. Keep the admitted destinations exact: intervention discontinuers move to comparator at the next annual boundary; comparator discontinuers leave the treated market.
7. Record annual full-cycle per-patient costs for both treatments, implementation costs, exclusions, evidence, assumptions, and provenance for every required numeric path.
8. Add at least one one-way sensitivity parameter and one alternative scenario. Vary only allowlisted numeric inputs and cite declared evidence or proposed assumptions.
9. State the annual-cycle event order and limitations. Stop for partial-cycle costing, re-initiation, combination therapy, more than two active treatments, treatment-specific mortality, disease-state migration, time-to-event calibration, or patient-level history.
10. Set `status` to `ready_for_human_review`, bind `base_analysis.content_sha256` to the final analysis-plan bytes, and run `scripts/validate_dynamic_budget_impact_plan.py heor/budget-impact-plan.json heor/analysis-plan.json`.
11. Ask the researcher to inspect the native dynamic flow ledger and authorize the existing analysis-plan gate. Never create an approval or claim independent validation.

## Interpretation boundary

- Treat all annual counts as expected values; fractional people are allowed.
- Charge a full budget-year cost to everyone allocated during that annual cycle.
- Allocate capacity to requested incident intervention starts before comparator displacement.
- Apply mortality after costs, then persistence among survivors, then boundary discontinuation destinations.
- Report requested, delivered, and unmet starts; opening and closing stocks; deaths; discontinuations; category costs; annual impact; and undiscounted cumulative impact.
- Label outputs as accounting calculations, not affordability thresholds, reimbursement recommendations, epidemiological forecasts, or scientific approval.
