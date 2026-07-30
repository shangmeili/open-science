---
name: heor-event-disutilities
description: Create, review, repair, or validate evidence-linked event-related QALY losses for AI4HEOR deterministic models. Use for adverse events, treatment-process burden, procedures, diagnostic consequences, one-time probabilities, recurrent expected events, continuous exposure, acute utility decrements, utility overlap review, or heor/event-disutilities.json. Do not use it to choose evidence autonomously, model long sequelae without explicit states, add event costs, execute component uncertainty, or claim Human approval.
---

# HEOR Event Disutilities

Prepare an auditable event ledger that remains separate from health-state utility inputs and reproduces every cycle/state QALY loss. Interact in natural language first; use structured fields to expose evidence, assumptions, overlap decisions, and arithmetic for Human review.

## Workflow

1. Read `heor/analysis-plan.json`, `heor/utility-inputs.json`, their linked evidence, and [references/method-boundary.md](references/method-boundary.md). Require analysis schema `0.15.0` and validated utility inputs. If either condition is not met, do not create or repair the reserved `heor/event-disutilities.json` path; keep any exploratory event-loss notes in `heor/event-disutilities.md` or another ordinary draft instead.
2. Ask the Human only about unresolved material choices: event inclusion and severity, affected strategy/states, mode, incidence or exposure schedule, absolute decrement, duration, day count, source transferability, and overlap policy.
3. Copy [assets/event-disutilities.template.json](assets/event-disutilities.template.json) to `heor/event-disutilities.json`. Bind the exact analysis and utility bytes with SHA-256.
4. Record terminology, severity, eligible states, occurrence schedule, health impact, and analysis-linked evidence for every item. Use `one_time`, `recurrent`, or `continuous_exposure` only as defined by the method boundary.
5. For every eligible utility item, add the exact `event_id` to its `excluded_effects`, keep it out of `captured_effects`, and name that utility item in `reviewed_utility_item_ids`. Stop if overlap remains unresolved.
6. Reproduce per-occurrence and per-cycle losses, then add item losses into `cycle_state_qaly_losses`. Evaluate every calculation before serialization and write only finite JSON number literals; never place arithmetic expressions, formula strings, `NaN`, or `Infinity` in numeric fields. Do not silently repair arithmetic or allow the implied utility to fall below -1.
7. Run the portable validator before Human review:

```bash
python3 runtime/skills/core/heor-event-disutilities/scripts/validate_event_disutilities.py \
  heor/analysis-plan.json heor/utility-inputs.json heor/event-disutilities.json
```

8. Report reproduced totals, exclusions, limitations, and unresolved Human decisions. State that recorded component uncertainty is not executed in this contract.

## Guardrails

- Never infer event inclusion, incidence, decrement, duration, severity, or overlap from availability alone.
- A non-continuous duration cannot exceed one model cycle; represent longer sequelae with explicit health or tunnel states.
- Keep event costs, interactions, caregiver spillovers, and component DSA/PSA outside this artifact.
- `ready_for_human_review` means reviewable, not approved, validated, or release-ready.
