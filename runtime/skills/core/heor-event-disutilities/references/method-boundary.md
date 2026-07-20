# AI4HEOR event-disutility method boundary 0.1.0

This contract makes event-related QALY-loss arithmetic and overlap controls reproducible. It does not decide which events or evidence are appropriate for a decision problem.

## Required Human decisions

The Human owns event inclusion and exclusion, terminology and severity, eligible strategy/states, occurrence mode and schedule, absolute utility decrement, duration, day-count convention, evidence transferability, additive combination, and overlap with health-state utilities. The agent may locate, compare, structure, calculate, and flag inconsistencies but must not silently choose among defensible alternatives.

## Deterministic boundary

The artifact uses an absolute utility decrement and exactly one of three modes:

- `one_time`: one probability from 0 to 1 in exactly one cycle. Per-cycle loss is `probability × decrement × duration_days / days_per_year`.
- `recurrent`: a non-negative expected event count per eligible person in each cycle. Per-cycle loss is `expected_events × decrement × duration_days / days_per_year`.
- `continuous_exposure`: an exposure fraction from 0 to 1 in each cycle. Per-cycle loss is `exposure_fraction × decrement × cycle_length_years`.

`days_per_year` is explicitly 365 or 365.25. A one-time or recurrent duration must not exceed one model cycle; persistent sequelae require explicit health or tunnel states. Item losses add by strategy, cycle, and eligible state under `additive_expected_qaly_loss`. The economic engine later weights these losses using the same state occupancy, half-cycle correction, and outcome discounting as health-state QALYs.

## Double-counting barrier

Every event item names exactly the health-state utility items for its eligible strategy/state pairs. Each named utility item must explicitly list the exact `event_id` in `excluded_effects` and must not list it in `captured_effects`. The event artifact binds the exact utility-input bytes. Validation stops on any missing exclusion, extra or missing reviewed utility item, stale hash, arithmetic drift, dead-state loss, or implied utility below -1.

This is a deterministic barrier, not proof that the source utility excludes the event. That evidence judgment remains Human-owned. Additivity can also overstate loss when events interact; record this limitation and use a different explicit model structure when interaction is material.

## Out of scope

Event costs, long-term sequelae without explicit states, caregiver spillovers, event interactions, autonomous evidence selection, and execution of component-level uncertainty are outside schema `0.1.0`. Uncertainty availability may be recorded, but the point schedule alone is executed.

## Method sources

- NICE PMG36, economic evaluation: https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2/
- Canada's Drug Agency, Guidelines for the Economic Evaluation of Health Technologies, fourth edition: https://www.cda-amc.ca/guidelines-economic-evaluation-health-technologies-canada-4th-edition
- NACI, Guidelines for the Economic Evaluation of Vaccination Programs in Canada: https://www.canada.ca/en/public-health/services/immunization/national-advisory-committee-on-immunization-naci/methods-process/incorporating-economic-evidence-federal-vaccine-recommendations/guidelines-evaluation-vaccination-programs-canada.html
- Value in Health, *Modeling Adverse Events in Health Economic Decision Models: A Review and Recommendations*: https://www.sciencedirect.com/science/article/pii/S1098301524001281
- Systematic review of adverse-event incorporation in economic models: https://pubmed.ncbi.nlm.nih.gov/36658308/
