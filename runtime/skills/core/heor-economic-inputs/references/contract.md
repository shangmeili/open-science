# AI4HEOR structure-neutral economic input contract 0.15.0

## Purpose

This contract separates economic rewards and reference-case settings from model structure. A partitioned survival model derives state occupancy from PFS and OS; it must not carry unused Markov initial distributions or transition definitions.

The common economic calculation uses state occupancy multiplied by state costs or utilities and cycle length. Without half-cycle correction it uses start-of-cycle occupancy and discounts at cycle start. With half-cycle correction it uses mean start/end occupancy and discounts at cycle midpoint.

## Required structure

The analysis plan must use schema `0.15.0`, link the partitioned-survival, cost, utility, and event-disutility artifacts, and define:

- one analysis ID, decision problem, reference case, and declared currency and price year;
- states exactly `progression_free`, `progressed`, and `dead` for the current PSM implementation;
- a positive cycle length, 1 to 10,000 cycles, non-negative cost and outcome discount rates, and a Boolean half-cycle correction;
- 2 to 16 unique safe strategy IDs, with the baseline first;
- for each strategy, exactly `name`, `state_costs`, and `state_utilities`.

Cost and utility arrays must match state order. Costs are finite and non-negative. Utilities are finite and from -1 to 1. Strategy names are non-empty and unique. Willingness-to-pay is optional and, when present, finite and non-negative.

`initial_distribution`, `transition_matrix`, and `transition_schedule` are forbidden. Survival curves and occupancy belong to partitioned-survival artifacts. Cost arithmetic belongs to `$heor-cost-input-normalization`; state utility schedules belong to `$heor-utility-inputs`; separately excluded event QALY losses belong to `$heor-event-disutilities`.

## Evidence boundary

Every required common input remains covered by the AI4HEOR input-provenance contract. Each component artifact binds exact analysis bytes and evidence IDs. Proposed assumptions remain review inputs and never become approvals. Earlier structure-neutral schemas remain readable under their narrower contracts.

## Method basis

The separation follows the decision-modeling distinction between model structure and model inputs. NICE PMG36 addresses the decision problem, health-state utilities, resource use and costs, discounting, and model-input source and precision as distinct considerations. ISPOR-SMDM state-transition guidance applies to transition models; NICE DSU partitioned-survival guidance treats PFS and OS as the occupancy basis. This contract therefore does not force a PSM through a transition-matrix schema.

Method sources:

- NICE, *Health technology evaluations: the manual*, economic evaluation, current PMG36 chapter.
- NICE Decision Support Unit, Technical Support Document 19, partitioned survival analysis.
- ISPOR-SMDM Modeling Good Research Practices Task Force, state-transition modeling.
- ISPOR health-state utility good-practices report.

## Human authority

Schema validity means only that the deterministic calculator has coherent inputs. It does not establish evidence quality, reference-case compliance, independent validation, cost effectiveness, reimbursement, or release approval.
