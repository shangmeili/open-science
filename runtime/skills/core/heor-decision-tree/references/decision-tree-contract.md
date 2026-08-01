# Decision-tree calculation contract

This contract covers a deterministic finite probability tree for short-horizon cost-effectiveness calculations. It is not a general event simulation and does not establish model validity.

## Admitted scope

- Schema and engine version: `0.1.0`; `analysis_type` is `decision_tree`.
- Horizon: greater than zero and at most one year.
- Strategies: 2–8 unique IDs; the first `strategy_order` entry is the baseline.
- Nodes: each strategy has one root, two or more branches per chance node, and terminal cost and QALY values.
- Topology: one connected acyclic tree per strategy. Every non-root node has exactly one parent and every node is reachable.
- Branch probabilities must sum to one within the engine tolerance and each probability must lie from zero to one.
- Terminal costs must be finite and non-negative. Terminal QALYs must be finite and lie between minus and plus the declared horizon.
- Discount rates are zero and half-cycle correction is false because this contract has no repeated cycles.

## Provenance and assumptions

Every probability, cost, and QALY is an object containing `value`, `source_ids`, and `assumption_ids`. At least one source or proposed assumption is required. Every `assumption_id` must refer to a top-level assumption whose status is `proposed`; the deterministic engine never accepts or approves it.

Source identifiers must resolve through the project's evidence and input-provenance records before formal use. A valid source ID proves only that the calculation records a locator; it does not prove eligibility, applicability, correctness, or Human acceptance.

## Deterministic output

The engine reports expected cost, expected QALY, optional net monetary benefit, a node-by-node calculation trace, pairwise increments versus baseline, the fully incremental frontier, and the strategy with highest net monetary benefit only when a willingness-to-pay threshold is present. The result binds the exact plan bytes through `input_sha256`.

The validator independently reparses and reruns the plan. When `--result` is provided, every result field must match deterministic replay. A changed plan, changed result, unsupported field, missing provenance, invalid topology, invalid number, or stale input hash fails closed.

## Human boundary

The Human researcher owns the decision problem, strategy set, tree structure, evidence eligibility and applicability, proposed assumptions, monetary basis, threshold, interpretation, and permitted use. A successful replay is calculation evidence, not approval, independent validation, or a reimbursement recommendation.
