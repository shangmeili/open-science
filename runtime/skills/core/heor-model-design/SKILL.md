---
name: heor-model-design
description: Create and audit HEOR decision-problem representations, conceptual models, health states, clinical pathways, structural assumptions, model-type rationale, structural alternatives, and validation questions. Use before approving a conceptual-model gate, translating evidence into a cohort state-transition model, or reviewing heor/conceptual-model.json for structural completeness and traceability.
---

# HEOR Model Design

Separate conceptualizing the decision problem from selecting a computational technique. Read `references/conceptual-model.md` before creating or changing the artifact.

## Workflow

1. Read the current decision question, evidence synthesis, and analysis plan. Do not infer an approval from either file.
2. Restate the objective, population, interventions, perspective, horizon, outcomes, and decision context.
3. Describe the clinical and care pathway before choosing a model type.
4. Define mutually understandable health states or events and allowed transitions. Explain how recurrence, treatment switching, adverse events, and death are represented or excluded.
5. Propose the simplest adequate model type and explain why its memory, timing, heterogeneity, and interaction assumptions fit the problem.
6. Record every material structural assumption as `unresolved`, `proposed`, or `rejected`; never use `accepted`.
7. Compare at least one plausible structural alternative and state what result or interpretation it could change.
8. Link structural claims to evidence-source IDs when available. Prespecify non-empty face, internal, and external validation plans plus questions that a later independent reviewer must test.
9. Write `heor/conceptual-model.json` from `assets/conceptual-model.template.json`, then run `scripts/validate_conceptual_model.py heor/conceptual-model.json heor/analysis-plan.json` so the analysis link is checked.
10. Ask the human to inspect the conceptual-model gate in the app only when the deterministic audit is complete.

## Boundaries

- Do not insert transition probabilities, costs, utilities, or other numeric model inputs into this artifact.
- A diagram is explanatory; the JSON artifact is the review contract.
- Do not choose a model because a package supports it. Match technique to the decision problem.
- Do not hide structural uncertainty inside parameter uncertainty.
- The app owns approval. A structurally complete artifact is only ready for human review, not approved or validated.

## Handoff

Report the artifact path, proposed model type, state and transition counts, structural assumptions, alternatives, unresolved items, and exact readiness for the conceptual-model human gate.
