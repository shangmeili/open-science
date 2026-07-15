---
name: heor-utility-inputs
description: Create, review, repair, or validate evidence-linked health-state utility inputs and cycle-specific utility schedules for AI4HEOR deterministic QALY models. Use for EQ-5D or other preference-based measures, value sets, direct valuation, mapping, respondent and population choices, age/comorbidity/population adjustment, licensing metadata, overlap and double-counting review, or heor/utility-inputs.json. Do not use it to select evidence autonomously, calculate event disutilities, or claim Human approval.
---

# HEOR Utility Inputs

Prepare one auditable health-state utility item for every strategy and state, then reproduce the exact cycle-specific utility schedule consumed by the model. Interact in natural language first; use structured fields only to make decisions and arithmetic reviewable.

## Workflow

1. Read the current `heor/analysis-plan.json`, its linked evidence, [references/method-boundary.md](references/method-boundary.md), and the applicable versioned reference-case profile. Do not assume a newly published or consulted value set is current guidance.
2. Ask the Human only for unresolved choices that materially change the result: target jurisdiction/population, instrument and version, respondent, valuation source or value set, mapping algorithm, adjustment method, captured effects, and overlap with separate event disutilities.
3. Create analysis schema `0.15.0` by retaining the cost link and adding the utility plus event-disutility links. Keep `state_utilities` equal to the first cycle of the declared schedule.
4. Copy [assets/utility-inputs.template.json](assets/utility-inputs.template.json) to `heor/utility-inputs.json`. Create exactly one item per `strategy_id` and `state_id`; use the unadjusted QALY anchor zero for every dead state.
5. Record measurement, valuation, license, mapping, source utility, uncertainty metadata, captured/excluded effects, and overlap rationale with analysis-linked evidence or proposed-assumption IDs. For mapped values, identify the source and target measure, algorithm, estimation population, validation evidence, performance evidence, and license.
6. Apply only explicit per-cycle multiplicative `age_adjustment`, `comorbidity_adjustment`, or `population_alignment` factors. Reproduce every `cycle_value` and every row in `cycle_state_utilities`; never repair arithmetic silently.
7. Keep acute or recurrent event disutilities outside this health-state schedule and route them to `$heor-event-disutilities`. Every separately modelled event ID must be named in the affected utility item's `excluded_effects`; stop if overlap cannot be resolved.
8. Run the portable validator before asking for Human review:

```bash
python3 runtime/skills/core/heor-utility-inputs/scripts/validate_utility_inputs.py \
  heor/analysis-plan.json heor/utility-inputs.json
```

9. Report what was reproduced, which choices remain Human-owned, license restrictions, mapping/transferability limitations, and that component-level utility uncertainty is recorded but not executed in this alpha.

## Guardrails

- Never choose an instrument, value set, mapping algorithm, respondent, population adjustment, or overlap policy merely because it is available.
- Never copy restricted scoring tables into the workspace when registration or a license permits only local use or linking.
- Never treat a consultation proposal as effective guidance; bind the dated reference-case profile and record the Human choice.
- Never describe `ready_for_human_review` as approved, verified, validated, or release-ready.
- Do not add event disutilities directly to this artifact; use the dedicated event contract. Caregiver effects and component uncertainty remain outside deterministic execution.
