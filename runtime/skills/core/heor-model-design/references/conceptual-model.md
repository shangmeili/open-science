# Conceptual model contract

The artifact is `heor/conceptual-model.json`. The desktop app independently repeats the structural audit before it allows a human conceptual-model approval.

## Required structure

- `schema_version`: `0.1.0`.
- `model_id` and `analysis_id`: stable non-empty identifiers; `analysis_id` must match the current `heor/analysis-plan.json`.
- `status`: `draft` or `ready_for_human_review`.
- `objective`: explicit decision-support objective.
- `scope`: non-empty population, intervention, comparator, perspective, time horizon, outcomes, jurisdiction, and decision context.
- `care_pathway`: ordered non-empty steps describing the represented clinical or care process.
- `model_type`: proposed technique and problem-based rationale.
- `states`: at least two unique IDs and labels; each state states whether it is absorbing.
- `transitions`: unique IDs whose `from` and `to` states exist. An absorbing state may only transition to itself.
- `structural_assumptions`: unique IDs, statements, rationales, and `unresolved`, `proposed`, or `rejected` status.
- `structural_alternatives`: at least one plausible alternative, rationale, and expected impact.
- `evidence_links`: source IDs for structural claims when available.
- `validation_questions`: non-empty questions for later face, internal, external, or cross-model validation.

`unresolved` assumptions block the app-owned conceptual-model gate. `proposed` means explicit and reviewable; it does not mean accepted. The app approval event is the only canonical human acceptance.

## Method basis

The [ISPOR-SMDM conceptualization report](https://www.ispor.org/publications/journals/value-in-health/abstract/Volume-15--Issue-6/Conceptualizing-a-Model--A-Report-of-the-ISPOR-SMDM-Modeling-Good-Research-Practices-Task-Force-2) separates problem conceptualization from model conceptualization and recommends agreement on the problem, perspective, population, interventions, outcomes, structure, and technique choice. The artifact follows that separation.

The validator proves only structural completeness and internal consistency. It cannot prove clinical validity, appropriateness of the model type, agreement by stakeholders, or independent validation.
