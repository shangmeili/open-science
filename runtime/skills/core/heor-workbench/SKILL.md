---
name: heor-workbench
description: Turn natural-language pharmacoeconomics and HEOR questions into auditable local research artifacts. Use for cost-effectiveness analysis, budget impact, evidence and model-input research, decision-problem scoping, conceptual models, analysis plans, deterministic model execution, result interpretation, sensitivity analysis planning, and review of files under heor/. Preserve human approval boundaries and never treat model output as an approval or policy recommendation.
---

# HEOR Workbench

Use conversation as the primary interface. Translate the researcher's intent into files and reproducible operations; ask for structured fields only when ambiguity would change the analysis.

## Operating boundary

- Treat the researcher as the decision owner and human reviewer.
- Never invent clinical inputs, prices, utilities, transition probabilities, comparators, thresholds, or citations.
- Separate sourced values, analyst assumptions, and unresolved inputs.
- Never add an `approvals` field to an analysis file or claim that a gate is approved. Approval is app-owned and requires a human action in the review panel.
- Treat deterministic calculations as calculations, not decisions. Do not label a result decision-ready.
- Use the configured model provider only for research assistance, synthesis, coding, and explanation. Keep numeric execution deterministic and reproducible.
- Keep data and artifacts inside the active project unless the researcher explicitly authorizes an external service.

## Natural-language workflow

1. Restate the decision question in one concise paragraph. Identify population, intervention, comparator, perspective, horizon, outcome, jurisdiction, and decision context.
2. List material unknowns before searching or modeling. Ask only questions that would change the model or interpretation.
3. Use `$heor-evidence-synthesis` when the question requires a reproducible search, screening, extraction, applicability, or conflict trail. Keep `heor/evidence-synthesis.json` separate from selected model inputs.
4. Use `$heor-model-design` to create or review `heor/conceptual-model.json`. Propose the smallest adequate structure, explicit structural assumptions, and plausible alternatives before the conceptual-model gate.
5. Create or update `heor/analysis-plan.json` from `assets/analysis-plan.template.json`. Read `references/analysis-plan.md` before editing it. Use `$heor-input-provenance` whenever evidence is selected for model inputs, mapped, audited, or prepared for analysis-plan review.
6. Use `$heor-reference-case` to assess every requirement in the selected versioned profile and bind `heor/reference-case-assessment.json` to the plan by exact content hash.
7. Tell the researcher exactly what changed, which inputs and reference-case requirements remain unsupported, and which review gate is ready for human inspection.
8. Run the deterministic engine only through the workbench review panel or its documented local command. Never recreate approval state in the workspace.
9. Interpret results in the conversation with the result classification, input hash, uncertainty limitations, and any validation still required.

## Evidence discipline

- Prefer guidelines, regulator or HTA sources, peer-reviewed methods papers, trial reports, registries, and official price or reimbursement sources.
- Quote sparingly. Attach each numeric input to a source or mark it explicitly as an assumption.
- Map every required engine input through `input_provenance`; external tools cannot bypass this contract.
- Record conflicting sources instead of silently selecting one.
- State the reference-case registry status exactly. `draft` guidance cannot authorize a locally approved analysis.
- Do not claim compliance merely because a named reference-case profile was selected. Require the independently audited, hash-bound compliance matrix.

## Analysis-plan handoff

The app watches `heor/analysis-plan.json`, `heor/conceptual-model.json`, and `heor/reference-case-assessment.json`. Keep them valid JSON and do not write temporary commentary into them. Use lower-case snake-case keys exactly as documented. Preserve unknown metadata fields created by the researcher or another tool. Independent artifacts are content-hashed; changing them requires renewed review.

After writing the plan, report:

- artifact path;
- unresolved inputs and assumptions;
- evidence gaps;
- recommended next human gate: decision problem, conceptual model, or analysis plan.

Do not ask the researcher to edit JSON unless they explicitly prefer that. Offer natural-language revisions such as “change the perspective to the Chinese healthcare system” and update the artifact yourself.
