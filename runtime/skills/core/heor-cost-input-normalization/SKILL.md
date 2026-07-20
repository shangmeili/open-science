---
name: heor-cost-input-normalization
description: Create, repair, audit, or explain AI4HEOR evidence-linked annual state-cost inputs. Use for resource quantities, unit prices, drug acquisition costs, price year, inflation, currency conversion, price adjustments, tax status, jurisdiction, perspective, or heor/cost-input-normalization.json; use before a partitioned-survival analysis consumes aggregate state_costs.
---

# HEOR Cost Input Normalization

Turn natural-language costing evidence into a deterministic, reviewable annual state-cost artifact. Keep form fields secondary to the conversation.

## Workflow

1. Read [references/cost-input-normalization-contract.md](references/cost-input-normalization-contract.md), the decision problem, economic basis, evidence synthesis, assumptions, and input provenance.
2. Confirm that the requested values are annual state-cost rates. Stop for event costs, one-time costs, time-varying prices, capital annualization, dynamic budget impact, or other unsupported structures.
3. Ask the researcher to resolve the cost perspective, included categories, price source, price basis, tax treatment, inflation index, exchange-rate method, and alternatives when evidence does not determine them. Never choose these from a plausible default.
4. Copy [assets/cost-input-normalization.template.json](assets/cost-input-normalization.template.json) to `heor/cost-input-normalization.json`. Replace every placeholder and bind the exact current `heor/analysis-plan.json` bytes.
5. Create one item per strategy, state, and resource. Record annual quantity and resource unit separately from the unit price. Link scope, quantity, price, and each adjustment to existing evidence, extraction, or proposed-assumption IDs.
6. Apply inflation exactly when price years differ and currency conversion exactly when currencies differ. Keep an optional price adjustment separate. Calculate `normalized_unit_price = source amount × all declared factors`, then `normalized_annual_cost = annual quantity × normalized unit price`.
7. Sum items in declared state order. Require `annual_state_costs` to reproduce the analysis plan's `state_costs` exactly within numerical tolerance; never repair either side silently.
8. Preserve confidential prices only in the local workspace and report their disclosure limitation. Do not copy credentials or confidential values into chat, logs, or exported examples.
9. Set `status` to `ready_for_human_review` only when every field and basis is reviewable. This is not approval.
10. Run:

```bash
python3 runtime/skills/core/heor-cost-input-normalization/scripts/validate_cost_input_normalization.py \
  heor/analysis-plan.json heor/cost-input-normalization.json
```

## Boundaries

- Validate arithmetic, exact analysis bytes, units, basis identifiers, and aggregate state costs; do not decide evidence quality or cost inclusion.
- Treat list, net, tariff, paid, negotiated, microcost, and opportunity-cost prices as different bases. Never call one another without an explicit adjustment and Human-reviewable basis.
- Do not infer discounts, rebates, taxes, inflation, exchange rates, purchasing-power parity, or local transferability.
- Do not mix inflation with discounting. Inflation standardizes the price basis; discounting handles future timing in the economic model.
- Keep event, one-time, time-varying, capital, societal, and dynamic-cohort structures outside this alpha unless they are legitimately represented as evidence-supported annual state rates.

## Deliverable

Return the artifact path, exact analysis binding, item and state totals, validator result, unresolved evidence/method choices, unsupported cost structures, and next Human review. Do not ask the researcher to edit JSON unless requested.
