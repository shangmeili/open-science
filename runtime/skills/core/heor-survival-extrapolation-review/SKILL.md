---
name: heor-survival-extrapolation-review
description: Prepare and audit AI4HEOR survival fitting and extrapolation reviews from an already-generated local fit bundle. Use when comparing a pre-specified set of standard parametric curves, separating observed and extrapolated time, recording statistical and graphical diagnostics, testing clinical and external plausibility, documenting structural alternatives, or preparing a curve recommendation for Human selection. This alpha imports exact survHE execution evidence but does not fit patient-level data; never auto-select a curve or claim scientific approval.
---

# HEOR Survival Extrapolation Review

Create `heor/survival-extrapolation-review.json` as an auditable comparison, not as an automatic model selector. Read `references/survival-extrapolation-contract.md` before preparing the artifact.

## Workflow

1. Read the decision problem, conceptual model, evidence synthesis, analysis plan, input provenance, and data classification. Confirm the endpoint, population, curve label, time origin, event and censor definitions, time unit, observed follow-up boundary, and modeled horizon in natural language.
2. Stop if the data classification or local execution boundary is unresolved. This alpha accepts only an already-generated local fit bundle and its manifest; do not open, transform, fit, or transmit patient-level input.
3. Pre-specify 2–8 candidate families before fitting. Use only the bounded first-slice families in the contract. Record why each candidate is included; do not add or remove a family after seeing results without declaring a protocol deviation.
4. Import execution evidence from a Human-controlled local R environment with pinned `survHE` and dependencies. Do not run the fit in this alpha, install packages silently, or bundle GPL code into the deterministic core. Capture the fit-bundle SHA-256, exact command or script SHA-256, R version, package versions, session information, and every generated fit/plot file hash.
5. Fit one absolute curve per artifact. Keep treatment-effect synthesis, proportional-hazards pooling, treatment switching, PFS/OS combination, competing risks, cure or mixture models, reconstructed IPD, and flexible splines outside this first contract.
6. Compare every pre-specified model. Record convergence, AIC, BIC, log likelihood, parameterization, common survival and hazard landmarks, Kaplan–Meier overlay, log-cumulative-hazard view, hazard view, and any protocol deviation. Failed fits remain visible.
7. Separate the observed period from extrapolation. Include at least one common landmark inside observed follow-up and one beyond it. Check survival monotonicity, non-negative hazards, expected hazard shape, external evidence, biological and clinical plausibility, and a representative structural scenario set.
8. Write an analyst recommendation only when its model is converged and all competing candidates remain visible. State why statistical fit alone is insufficient and identify at least one alternative. Set the gate state only to `awaiting_human_selection`.
9. Run `scripts/validate_survival_extrapolation_review.py heor/survival-extrapolation-review.json --workspace <project-root>`. Fix structural, hash, landmark, or completeness errors. The desktop analysis-plan approval remains authoritative for the selected curve and downstream use.
10. After Human selection, route only a supported already-selected exponential or Weibull absolute curve to `$heor-survival-curve-adapter`. Keep other families and all unresolved clinical validity questions explicit until a separately admitted calculation contract exists.

## Boundaries

- Do not auto-rank or auto-select by AIC, BIC, visual fit, or a composite score.
- Do not hide failed models, post-hoc family changes, implausible tails, or uncertainty outside the trial period.
- Do not convert a recommendation, review basis, plot, package output, or agent statement into approval.
- Do not claim that a checklist establishes internal validity, external validity, proportional hazards, independent validation, reimbursement suitability, or policy advice.
- Do not execute an external fitting package in this alpha. A future isolated backend requires a separately admitted patient-level data and app-owned execution contract.

## Resources

- `references/survival-extrapolation-contract.md`: exact artifact, method, execution, and stopping rules.
- `assets/survival-extrapolation-review.template.json`: copyable draft artifact.
- `scripts/validate_survival_extrapolation_review.py`: standalone structural, landmark, hash, and Human-gate validator.
