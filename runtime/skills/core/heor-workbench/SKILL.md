---
name: heor-workbench
description: Turn natural-language pharmacoeconomics and HEOR questions into auditable local research artifacts. Use for cost-effectiveness analysis, budget impact, evidence and model-input research, decision-problem scoping, conceptual models, analysis plans, deterministic model execution, result interpretation, sensitivity analysis planning, affordability analysis, and review of files under heor/. Preserve human approval boundaries and never treat model output as an approval or policy recommendation.
---

# HEOR Workbench

Use conversation as the primary interface. Translate the researcher's intent into files and reproducible operations; ask for structured fields only when ambiguity would change the analysis.

## Operating boundary

- Treat the researcher as the decision owner and human reviewer.
- Never invent clinical inputs, prices, utilities, transition probabilities, comparators, thresholds, or citations.
- Never silently combine monetary inputs with different currencies or price years. Declare one calculation basis and preserve every adjustment as a reproducible, sourced transformation.
- Never copy an extracted value into a model input without an executable derivation. Direct evidence must be strict JSON equal to the model value; unsupported transformations remain blocked.
- Separate sourced values, analyst assumptions, and unresolved inputs.
- Never add an `approvals` field to an analysis file or claim that a gate is approved. Approval is app-owned and requires a human action in the review panel.
- Treat deterministic calculations as calculations, not decisions. Do not label a result decision-ready.
- Use the configured model provider only for research assistance, synthesis, coding, and explanation. Keep numeric execution deterministic and reproducible.
- Keep data and artifacts inside the active project unless the researcher explicitly authorizes an external service.

## Natural-language workflow

1. Restate the decision question in one concise paragraph. Identify population, intervention, comparator, perspective, horizon, outcome, jurisdiction, and decision context.
2. List material unknowns before searching or modeling. Ask only questions that would change the model or interpretation.
3. Use `$heor-local-evidence` for project-local PDF or text knowledge-base retrieval. Require the app-owned hash manifest and cite the exact path, SHA-256, and page; never treat OCR-required or failed extraction as reviewed evidence.
4. Use `$heor-evidence-search` to draft and validate a bounded PubMed/ClinicalTrials.gov metadata request when public-source retrieval is needed. Never execute or bypass the app-owned human network authorization; import app-written results only as `not_assessed` candidates.
5. Use `$heor-evidence-synthesis` for screening, extraction, applicability, critical appraisal, or conflict trails. Keep `heor/evidence-synthesis.json` separate from retrieved candidates and selected model inputs.
6. Use `$heor-model-design` to create or review `heor/conceptual-model.json`. Propose the smallest adequate structure, explicit structural assumptions, and plausible alternatives before the conceptual-model gate.
7. Use `$heor-cohort-state-transition` when translating the conceptual model into static or piecewise model-cycle-dependent transitions. When evidence supplies constant cause-specific competing event rates instead of cycle probabilities, use `$heor-transition-rate-adapter`; stop rather than inventing a broader conversion or using a schedule to imitate material time-in-state, patient history, interactions, or heterogeneity.
8. Create or update `heor/analysis-plan.json` from `assets/analysis-plan.template.json`. Read `references/analysis-plan.md` before editing it. Obtain the calculation currency and price year through natural-language scoping; do not silently keep the template example. Use `$heor-input-provenance` whenever evidence is selected for model inputs, mapped, deterministically transformed, economically normalized, audited, or prepared for analysis-plan review.
9. Select exactly one bundled profile from the stated decision jurisdiction, then use `$heor-reference-case` to assess every requirement and bind `heor/reference-case-assessment.json` to the plan by exact content hash. Use `NICE-PMG36-2026-current` only for England; never silently default an England analysis to a China profile or merge jurisdictions.
10. Use `$heor-uncertainty-analysis` to create and validate schema `0.4.0` `heor/uncertainty-plan.json`. Bind it to the exact current analysis-plan bytes; derive ranges, distributions, and any lognormal correlation matrix only from linked evidence, preserve omissions, unsupported dependence, convergence thresholds, and structural scenarios, and obtain the CEAC/CEAF threshold range from the natural-language decision context or explicit human instruction. For admitted schema `0.5.0` transitions, use exact event-rate targets so full transition inputs are recomputed per run. Never invent a jurisdictional threshold, repair a correlation matrix, or vary a derived probability row.
11. Use `$heor-budget-impact` when affordability or payer expenditure is in scope. Create `heor/budget-impact-plan.json` as a separate three-year, undiscounted, two-scenario cost calculator bound to the exact analysis-plan bytes; do not derive it from discounted cost-effectiveness totals.
12. Use `$heor-model-validation` after the analysis artifacts are stable to prepare or audit `heor/model-validation.json` and local evidence. Never fill the independent reviewer's declaration or recommendation, identify Agent work as independent review, or create validation approval.
13. After all three app-written result artifacts and a current independent-validation approval exist, use `$heor-reporting` to prepare or audit the separate CHEERS 2022 cost-effectiveness matrix, ISPOR BIA matrix, report, exact result summary, disclosures, and hash-bound release package. Never edit result files, invent the release owner, score reporting quality, or create release approval.
14. Tell the researcher exactly what changed, which model and BIA inputs, reference-case requirements, uncertainty components, validation checks, and reporting items remain unsupported, and which review gate is ready for human inspection.
15. Run deterministic base-case, uncertainty, or budget impact calculations only through the workbench review panel or its documented local command. Never recreate approval state in the workspace.
16. Interpret results in the conversation with the result classification, exact input hashes, Monte Carlo or budget diagnostics, limitations, validation, reporting, and release status. Explain CEAC and CEAF separately and describe EVPI only as a per-person upper bound over uncertainty represented in the current PSA; do not infer population EVPI, EVPPI, research funding, study design, reimbursement, or policy advice.

## Evidence discipline

- Prefer guidelines, regulator or HTA sources, peer-reviewed methods papers, trial reports, registries, and official price or reimbursement sources.
- Quote sparingly. Attach each numeric input to a source or mark it explicitly as an assumption.
- Map every required engine input through approvable schema `0.3.0`, `0.4.0`, or `0.5.0` `input_provenance`, including an exact derivation snapshot. Reserve `0.5.0` for the admitted deterministic transition-rate transformation, and never let external tools bypass this contract.
- Record conflicting sources instead of silently selecting one.
- State the reference-case registry status exactly. `draft` guidance cannot authorize a locally approved analysis.
- Do not claim compliance merely because a named reference-case profile was selected. Require the independently audited, hash-bound compliance matrix.

## Analysis-plan handoff

The app watches `heor/evidence-search-request.json`, app-written files under `heor/evidence-search-runs/`, `heor/analysis-plan.json`, `heor/conceptual-model.json`, `heor/reference-case-assessment.json`, `heor/uncertainty-plan.json`, `heor/budget-impact-plan.json`, `heor/model-validation.json`, `heor/report-package.json`, `heor/report.md`, and app-written files under `heor/results/`. Keep JSON files valid and do not write temporary commentary into them. Keep validation evidence under `heor/validation-evidence/`. Use lower-case snake-case keys exactly as documented. Preserve unknown metadata fields created by the researcher or another tool. Independent artifacts are content-hashed; changing them requires renewed review.

After writing the plan, report:

- artifact path;
- unresolved inputs and assumptions;
- evidence gaps;
- recommended next human gate: decision problem, conceptual model, analysis plan, independent validation, or release.

Do not ask the researcher to edit JSON unless they explicitly prefer that. Offer natural-language revisions such as “change the perspective to the Chinese healthcare system” and update the artifact yourself.
