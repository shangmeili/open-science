# Decision-tree calculation contract

This contract covers a deterministic finite probability tree for short-horizon cost-effectiveness calculations. It is not a general event simulation and does not establish model validity.

## Admitted scope

- Current schema and engine version: `0.2.0`; `analysis_type` is `decision_tree`.
- Current plans require exactly one economic basis containing a three-letter uppercase currency code, an integer price year from 1900 through 2100, a non-empty jurisdiction, and a non-empty analysis perspective.
- Legacy schema and engine `0.1.0` remain calculable only for deterministic replay of existing work. They do not claim an economic basis and their monetary results are exploratory, not eligible for formal reporting.
- Horizon: greater than zero and at most one year.
- Strategies: 2–8 unique IDs; the first `strategy_order` entry is the baseline.
- Nodes: each strategy has one root, two or more branches per chance node, and terminal cost and QALY values.
- Topology: one connected acyclic tree per strategy. Every non-root node has exactly one parent and every node is reachable.
- Branch probabilities must sum to one within the engine tolerance and each probability must lie from zero to one.
- Terminal costs must be finite and non-negative. Terminal QALYs must be finite and lie between minus and plus the declared horizon.
- Discount rates are zero and half-cycle correction is false because this contract has no repeated cycles.

## Provenance and assumptions

Every probability, cost, and QALY is an object containing `value`, `source_ids`, and `assumption_ids`. At least one source or proposed assumption is required. Every `assumption_id` must refer to a top-level assumption whose status is `proposed`; the deterministic engine never accepts or approves it.

The engine preserves the declared currency, price year, jurisdiction, and perspective in the result. It does not perform exchange-rate conversion, monetary adjustment, or perspective inference.

Source identifiers must resolve through the project's evidence and input-provenance records before formal use. A valid source ID proves only that the calculation records a locator; it does not prove eligibility, applicability, correctness, or Human acceptance.

## Deterministic output

The engine reports expected cost, expected QALY, optional net monetary benefit, a node-by-node calculation trace, pairwise increments versus baseline, the fully incremental frontier, and the strategy with highest net monetary benefit only when a willingness-to-pay threshold is present. The result binds the exact plan bytes through `input_sha256`.

The validator independently reparses and reruns the plan. When `--result` is provided, every result field must match deterministic replay. A changed plan, changed result, unsupported field, missing provenance, invalid topology, invalid number, or stale input hash fails closed.

## DSA and PSA companion contract

Decision-tree uncertainty schema/engine `0.1.0` requires an exact SHA-256 binding to a current decision-tree `0.2.0` plan and a positive willingness-to-pay threshold. It never accepts legacy decision-tree `0.1.0` because those monetary results have no declared economic basis.

Each parameter targets exactly one binary branch probability plus its named complement, one terminal cost, or one terminal QALY. Probability replacement is admitted only for a two-branch chance node; the engine assigns the explicit complement to `1-p` and never normalizes a multi-branch node. Multiple parameters may not mutate the same value. Every deterministic range and probabilistic distribution must cite IDs already attached to the targeted value.

The contract admits bounded Uniform for all targets, Beta for binary probabilities, and Gamma or Lognormal for terminal costs. It does not infer a distribution from a point estimate. The plan must supply a fixed PCG32 seed, 100–10,000 iterations, at least two increasing convergence checkpoints ending at the iteration count, probability MCSE and drift thresholds no greater than 0.1, an independence rationale, and known omissions. Every sample is retained with its parameter values and strategy outcomes; unique optima and ties are reported separately. A passed convergence diagnostic describes Monte Carlo precision for the declared run only. This is represented parameter uncertainty, not structural uncertainty, evidence validation, or independent model validation.

## Human boundary

The Human researcher owns the decision problem, strategy set, tree structure, evidence eligibility and applicability, proposed assumptions, currency, price year, jurisdiction, perspective, threshold, interpretation, and permitted use. A successful replay is calculation evidence, not approval, independent validation, or a reimbursement recommendation.
