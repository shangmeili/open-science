# Dynamic budget impact contract

Schema `0.2.0` reuses `heor/budget-impact-plan.json` and the existing app-owned analysis-plan and release gates. It does not replace or reinterpret legacy schema `0.1.0`.

## Annual state update

For each scenario and year, calculate in this exact order:

1. Start from the previous closing comparator and intervention stocks; year 1 starts from `initial_prevalent` split by `initial_intervention_share`.
2. Add the incident cohort. Request intervention starts using `incident_intervention_share_by_year`; unserved incident starts remain on comparator.
3. Request comparator displacement from the comparator stock after incident allocation. Apply remaining intervention-start capacity after prioritizing incident starts.
4. Charge full-year per-patient costs to the resulting treated stocks and add scenario-level implementation costs.
5. Apply the common annual mortality probability to both treatment stocks.
6. Apply treatment-specific continuation probabilities among survivors. Intervention discontinuers enter comparator at the next annual boundary; comparator discontinuers exit the treated market.

The model reports expected counts and does not round people. `intervention_start_capacity_by_year` covers incident plus displaced starts, not continuing intervention patients.

## Required provenance

Bind every numeric leaf under:

- initial prevalence and three incident cohorts;
- three annual mortality probabilities;
- both scenarios' initial share, three incident shares, three displacement shares, and three capacities;
- both strategies' three continuation probabilities;
- every annual per-patient and implementation cost.

Each mapping records unit, jurisdiction, selection rationale, uncertainty status, evidence or a proposed assumption, and price year for monetary inputs.

## Stop boundary

Reject partial-year entry or costing, treatment re-initiation, multiple discontinuation destinations, treatment-specific mortality, capacity queues across years, combination therapy, induced diagnosis, severity or disease-state transitions, more than two active treatments, individual history, and automatic parameter estimation. Use a separately admitted cohort or patient-level adapter when these materially affect the question.
