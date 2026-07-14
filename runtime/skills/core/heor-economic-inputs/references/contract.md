# AI4HEOR structure-neutral economic input contract 0.12.0

## Purpose

This contract separates economic rewards and reference-case settings from model structure. A partitioned survival model derives state occupancy from PFS and OS; it must not carry unused Markov initial distributions or transition definitions.

The common economic calculation uses state occupancy multiplied by state costs or utilities and cycle length. Without half-cycle correction it uses start-of-cycle occupancy and discounts at cycle start. With half-cycle correction it uses mean start/end occupancy and discounts at cycle midpoint.

## Required structure

The analysis plan must use schema `0.12.0`, link exactly `heor/partitioned-survival-plan.json`, and define:

- one analysis ID, decision problem, reference case, and declared currency and price year;
- states exactly `progression_free`, `progressed`, and `dead` for the current PSM implementation;
- a positive cycle length, 1 to 10,000 cycles, non-negative cost and outcome discount rates, and a Boolean half-cycle correction;
- 2 to 16 unique safe strategy IDs, with the baseline first;
- for each strategy, exactly `name`, `state_costs`, and `state_utilities`.

Cost and utility arrays must match state order. Costs are finite and non-negative. Utilities are finite and from -1 to 1. Strategy names are non-empty and unique. Willingness-to-pay is optional and, when present, finite and non-negative.

`initial_distribution`, `transition_matrix`, and `transition_schedule` are forbidden. Survival curves, their selection, and occupancy derivation belong to the partitioned-survival artifacts.

## Evidence boundary

Every required common input must remain covered by the AI4HEOR input-provenance contract. Economic normalization must identify source currency and price year, adjustment factors, and exact selected extraction elements. Proposed assumptions remain review inputs and never become approvals through this contract.

## Method basis

The separation follows the decision-modeling distinction between model structure and model inputs. NICE PMG36 addresses the decision problem, health-state utilities, resource use and costs, discounting, and model-input source and precision as distinct considerations. ISPOR-SMDM state-transition guidance applies to transition models; NICE DSU partitioned-survival guidance treats PFS and OS as the occupancy basis. This contract therefore does not force a PSM through a transition-matrix schema.

Method sources:

- NICE, *Health technology evaluations: the manual*, economic evaluation, current PMG36 chapter.
- NICE Decision Support Unit, Technical Support Document 19, partitioned survival analysis.
- ISPOR-SMDM Modeling Good Research Practices Task Force, state-transition modeling.
- ISPOR health-state utility good-practices report.

## Human authority

Schema validity means only that the deterministic calculator has coherent inputs. It does not establish evidence quality, reference-case compliance, independent validation, cost effectiveness, reimbursement, or release approval.
