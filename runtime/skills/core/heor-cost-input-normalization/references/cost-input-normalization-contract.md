# AI4HEOR cost-input normalization contract 0.1.0

## Scope

The artifact `heor/cost-input-normalization.json` decomposes each model annual state-cost rate into explicit resource quantities and unit prices. It is a deterministic costing ledger, not an authority for the analysis perspective, included resources, source selection, opportunity-cost interpretation, price basis, tax treatment, transferability, or reimbursement decisions.

The current bounded calculation is:

```text
normalized unit price = source unit price × product(declared adjustment factors)
normalized annual cost = annual resource quantity × normalized unit price
annual state cost = sum(normalized annual item costs for strategy and state)
```

The economic model subsequently multiplies the annual state-cost rate by state occupancy and cycle length. Event costs, one-time costs, time-varying prices, capital annualization, capacity effects, and dynamic cohorts need distinct structures and must not be forced into this contract.

## Required bindings

- schema `0.1.0`, safe normalization and item IDs, and `ready_for_human_review` status;
- exact path and SHA-256 of `heor/analysis-plan.json`;
- target currency and price year matching `economic_basis`;
- target jurisdiction and perspective matching the decision problem;
- exact analysis strategy order and state order;
- 1–1,000 ordered resource items and an exact aggregate array for every strategy;
- at least one explicit limitation.

Each item declares strategy, state, category, description, scope basis, positive annual quantity, resource unit, source unit price, source currency/year/jurisdiction, price basis, tax status, adjustments, normalized unit price, and normalized annual cost. The unit-price denominator must equal the quantity unit.

`inflation` is required exactly when source and target price years differ. `currency_conversion` is required exactly when currencies differ. `price_adjustment` is optional for an explicitly justified additional multiplicative adjustment. Each kind may occur at most once, must be positive and finite, and must link to evidence, an extraction, or a proposed assumption already present in the analysis.

## Human authority

Arithmetic validity does not establish that a resource belongs in the perspective, a price reflects opportunity cost, a confidential agreement remains current, an index or exchange rate is appropriate, or a foreign cost is transferable. Those remain explicit Human method and evidence decisions. A changed analysis file invalidates the artifact.

## Method basis

- NICE PMG36 requires systematic identification of resource use and costs, prices relevant to the selected perspective, acknowledgement of price uncertainty, appropriate inflation indices, and appropriate exchange-rate sources. It distinguishes CEA from budget impact tax treatment.
- Canadian public guidance requires resources to be systematically identified, measured, valued, and reported, using jurisdiction-relevant sources and values that reflect opportunity cost for the perspective.
- WHO OneHealth describes ingredients-based costing as quantities multiplied by prices.
- The ISPOR Drug Cost Task Force distinguishes active-ingredient units, local-currency prices, price-year adjustment, and subsequent currency conversion.

These sources guide the review fields and failure boundaries. They do not supply jurisdiction-independent defaults.
