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

1. Restate the decision question in one concise paragraph. Identify population, all relevant strategies, perspective, horizon, outcome, jurisdiction, and decision context.
2. List material unknowns before searching or modeling. Ask only questions that would change the model or interpretation.
3. Use `$heor-local-evidence` for project-local PDF or text knowledge-base retrieval. Require the app-owned hash manifest and cite the exact path, SHA-256, and page; never treat OCR-required or failed extraction as reviewed evidence.
4. Use `$heor-evidence-search` to draft and validate a bounded PubMed/ClinicalTrials.gov metadata request when public-source retrieval is needed. Never execute or bypass the app-owned human network authorization; import app-written results only as `not_assessed` candidates.
5. Use `$heor-evidence-synthesis` for screening, extraction, applicability, critical appraisal, or conflict trails. Keep `heor/evidence-synthesis.json` separate from retrieved candidates and selected model inputs.
6. Use `$heor-model-design` to create or review `heor/conceptual-model.json`. Propose the smallest adequate structure, explicit structural assumptions, and plausible alternatives before the conceptual-model gate.
7. Use `$heor-cohort-state-transition` when translating the conceptual model into transitions. Use `$heor-transition-rate-adapter` for admitted constant competing rates, `$heor-survival-curve-adapter` for an already-selected exponential or Weibull absolute curve in exactly two states, `$heor-probability-time-adapter` only for one absolute event probability with an explicit source interval, `$heor-background-mortality` for its bounded additive mortality case, and `$heor-relative-effect-adapter` only for cycle-specific baseline risks plus one aligned RR or OR. Route HR to a future `$heor-hazard-ratio-adapter`; stop rather than coercing effect measures, combining competing probabilities, fitting or selecting curves, or inventing treatment-effect extrapolation.
8. Create or update `heor/analysis-plan.json`. Use `assets/multi-strategy-analysis-plan.template.json` and schema `0.8.0` for ordinary multi-strategy work, schema `0.9.0` only for background mortality, and schema `0.10.0` only for the admitted RR/OR relative-effect contract; use `assets/analysis-plan.template.json` only to preserve a legacy two-role project. Read `references/analysis-plan.md` before editing. Obtain the calculation currency and price year through natural-language scoping; do not silently keep a template example. Use `$heor-input-provenance` whenever evidence is selected for model inputs, mapped, deterministically transformed, economically normalized, audited, or prepared for review.
9. Select exactly one bundled profile from the stated decision jurisdiction, then use `$heor-reference-case` to assess every requirement and bind `heor/reference-case-assessment.json` to the plan by exact content hash. Use `NICE-PMG36-2026-current` only for England; never silently default an England analysis to a China profile or merge jurisdictions.
10. Use `$heor-uncertainty-analysis` to create and validate `heor/uncertainty-plan.json`. Pair analysis/uncertainty `0.8.0`/`0.7.0`, background mortality `0.9.0`/`0.8.0`, and relative effect `0.10.0`/`0.9.0` exactly. Under `0.10.0`, target only `relative_effect.value`: RR uses bounded Uniform support below `1/max(baseline q>0)` and OR uses Lognormal or strictly positive Uniform. Bind exact plan bytes and never invent ranges, distributions, correlations, thresholds, curve choices, effect constancy, or derived-row values.
11. Use `$heor-budget-impact` when affordability or payer expenditure is in scope. Create `heor/budget-impact-plan.json` as a separate three-year, undiscounted, two-scenario cost calculator bound to the exact analysis-plan bytes; do not derive it from discounted cost-effectiveness totals.
12. Use `$heor-model-validation` after the analysis artifacts are stable to prepare or audit `heor/model-validation.json` and local evidence. Never fill the independent reviewer's declaration or recommendation, identify Agent work as independent review, or create validation approval.
13. After all three app-written result artifacts and a current independent-validation approval exist, use `$heor-reporting` to prepare or audit the separate CHEERS 2022 cost-effectiveness matrix, ISPOR BIA matrix, report, exact result summary, disclosures, and hash-bound release package. Never edit result files, invent the release owner, score reporting quality, or create release approval.
14. Tell the researcher exactly what changed, which model and BIA inputs, reference-case requirements, uncertainty components, validation checks, and reporting items remain unsupported, and which review gate is ready for human inspection.
15. Run deterministic base-case, uncertainty, or budget impact calculations only through the workbench review panel or its documented local command. Never recreate approval state in the workspace.
16. Interpret results in the conversation with the result classification, exact input hashes, Monte Carlo or budget diagnostics, limitations, validation, reporting, and release status. Explain CEAC and CEAF separately and describe EVPI only as a per-person upper bound over uncertainty represented in the current PSA; do not infer population EVPI, EVPPI, research funding, study design, reimbursement, or policy advice.

## Evidence discipline

- Prefer guidelines, regulator or HTA sources, peer-reviewed methods papers, trial reports, registries, and official price or reimbursement sources.
- Quote sparingly. Attach each numeric input to a source or mark it explicitly as an assumption.
- Map every required engine input through approvable portable schema `0.3.0` through `0.10.0`, including an exact derivation snapshot. Schema `0.9.0` adds bounded background mortality; schema `0.10.0` adds only bounded RR/OR application with exact endpoint, population, and effect-constancy review bases. Review bases remain evidence or proposed assumptions and never act as approval. Never let external tools bypass this contract.
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
