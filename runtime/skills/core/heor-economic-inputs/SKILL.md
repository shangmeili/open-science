---
name: heor-economic-inputs
description: Create, repair, or validate AI4HEOR model-structure-neutral economic inputs for partitioned survival analyses. Use when costs, utilities, cycle settings, discounting, willingness-to-pay, or strategy order must be defined without inventing an initial distribution, transition matrix, or transition schedule.
---

# HEOR Economic Inputs

Translate a natural-language economic analysis scope into the common, deterministic inputs in `heor/analysis-plan.json` schema `0.14.0`. Keep survival structure, cost decomposition, and utility construction in their dedicated artifacts.

## Workflow

1. Read [references/contract.md](references/contract.md), the decision problem, selected evidence, assumptions, and reference-case assessment.
2. Confirm that partitioned survival is the intended structure and that the states are exactly `progression_free`, `progressed`, and `dead` in that order. Otherwise stop and route to the relevant model-design Skill.
3. Copy [assets/partitioned-survival-analysis-plan.template.json](assets/partitioned-survival-analysis-plan.template.json) to `heor/analysis-plan.json`, replace every placeholder, and link `heor/cost-input-normalization.json` plus `heor/utility-inputs.json` without embedding their hashes.
4. Capture currency, price year, cycle grid, discount rates, half-cycle correction, optional willingness-to-pay, ordered strategies, and state rewards. Obtain missing choices through natural-language conversation; use form fields only as an entry aid.
5. Keep each strategy object exactly to `name`, `state_costs`, and `state_utilities`. Do not add `initial_distribution`, `transition_matrix`, or `transition_schedule`.
6. Use `$heor-cost-input-normalization` to decompose every annual state-cost rate, `$heor-utility-inputs` to reproduce every cycle-specific state utility, and `$heor-input-provenance` to bind every required input to evidence or an explicit proposed assumption. Do not invent or silently normalize costs, utilities, thresholds, or time bases.
7. Leave `input_status` incomplete and report blockers until every required value and derivation is reviewable.
8. Run:

```bash
python3 runtime/skills/core/heor-economic-inputs/scripts/validate_economic_inputs.py \
  heor/analysis-plan.json
```

## Boundaries

- This Skill specifies economic inputs; it does not choose or materialize survival curves, calculate state occupancy, fit models, or select a model structure.
- Costs must be finite, non-negative annual state rates exactly reproduced by the cost artifact. First-cycle utilities must be finite from -1 to 1 and exactly reproduced by the utility artifact; later cycles are consumed from its explicit schedule. Arrays follow the declared state order.
- `ready_for_human_review` means structurally reviewable, not approved or decision-ready.
- Keep approval, revocation, independent validation, and release authority in the desktop app.
- If evidence is missing or conflicting, preserve the gap; never fill it with a plausible value.

## Deliverable

Return the analysis-plan path, validator result, unresolved inputs, provenance gaps, and next required Human review. Do not ask the researcher to edit JSON unless they request it.
