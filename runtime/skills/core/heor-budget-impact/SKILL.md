---
name: heor-budget-impact
description: Create, audit, and explain a hash-bound three-year payer budget impact plan using explicit eligible populations, without/with-access market shares, itemized treatment and condition-related costs, implementation costs, one-way sensitivity analyses, and alternative scenarios. Use when preparing or repairing heor/budget-impact-plan.json, estimating affordability or annual payer expenditure, translating uptake and population evidence into a transparent cost calculator, or preparing the analysis-plan human gate without claiming reimbursement approval or independent validation.
---

# HEOR Budget Impact

Create a transparent local cost calculator; do not reuse the discounted cost-effectiveness result as a budget impact estimate. Read `references/budget-impact-contract.md` before changing the artifact.

## Workflow

1. Read the exact current bytes of `heor/analysis-plan.json`. Confirm that it links `heor/budget-impact-plan.json` and has a jurisdiction. For schema `0.8.0`, explicitly select two distinct declared strategy IDs as the displaced comparator and new intervention for this bounded BIA.
2. Define the budget holder, jurisdiction, currency, price year, and perspective-aligned cost boundary. Record excluded cost categories with a rationale.
3. Estimate the eligible treated population independently for each of three annual budget cycles. Preserve the derivation and distinguish synthetic assumptions from evidence.
4. Define without-access and with-access scenarios. In this two-strategy MVP, the new-intervention share is zero without access; the comparator share is derived as one minus the intervention share.
5. Itemize included intervention and condition-related annual per-patient costs for both strategies. Add scenario-level implementation costs separately; do not hide them inside per-patient values.
6. Map every annual population, with-access uptake, included per-patient cost, and implementation total to evidence or a `proposed` assumption through `input_provenance`. Costs require currency units and price years.
7. Add evidence-bound one-way ranges that bracket base values and at least one plausible alternative scenario. Vary only allowlisted numeric inputs; never target identifiers, status, evidence, hashes, perspective, or authority fields.
8. Plan face, internal, and external validation without claiming that any validation occurred. Record limitations, including unsupported induced demand, multiple treatments, or dynamic cohort entry/exit when material.
9. Set `status` to `ready_for_human_review`, bind `base_analysis.content_sha256` to the final exact analysis-plan bytes, and write `heor/budget-impact-plan.json` from the bundled template.
10. Run `scripts/validate_budget_impact_plan.py heor/budget-impact-plan.json heor/analysis-plan.json`. The desktop repeats and extends this audit before approval or execution.

## Boundaries

- Never discount budget impact cash flows in this MVP; report annual and cumulative nominal budget-cycle values.
- Never infer affordability from cost-effectiveness, or present budget impact as a reimbursement recommendation.
- Never invent population, uptake, price, utilization, or cost-offset inputs.
- Never create approval events, accept analyst assumptions, or claim independent validation.
- Keep confidential prices local and out of logs, exports, screenshots, and public reports unless the researcher explicitly authorizes their handling.
- Stop at the two-share cost-calculator boundary when induced demand, population churn, severity mix, combination therapy, or more than two active market shares materially affect the question; a multi-strategy CEA does not make this pairwise BIA a multi-treatment market model.

## Handoff

Report the analysis and BIA IDs, exact hashes, budget holder, currency and price year, three annual populations and uptake values, included/excluded costs, annual and cumulative impact, leading sensitivity driver, alternative scenarios, provenance gaps, validation still required, and the next natural-language repair. Label every output as a calculation, not a decision.
