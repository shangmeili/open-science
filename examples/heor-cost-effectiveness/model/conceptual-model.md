# Conceptual model for Human review

## Intended use

Teach a complete, local, reproducible cost-utility workflow. The model is not
intended to support a real clinical, pricing, reimbursement, or policy decision.

## Structure

The closed cohort starts with 1,000 people in `stable` and moves once per year
among three mutually exclusive states:

`stable -> progressed -> dead`

Death is absorbing. Return from `progressed` to `stable` is excluded. Costs and
utilities accrue from average start- and end-of-cycle occupancy. This implements
a trapezoidal half-cycle correction. Costs and health outcomes are discounted
at the end of each cycle.

## Key exclusions

- age- or sex-specific mortality;
- treatment discontinuation, waning, adverse events, and treatment sequences;
- recurrent events, time since entry, and patient history;
- heterogeneity, subgroups, and patient-level simulation;
- calibration, competing background mortality, and external validation;
- parameter correlation and evidence-synthesis uncertainty.

Every inclusion and exclusion above remains a Human-owned conceptual-model
choice in a real evaluation.
