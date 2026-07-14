---
name: heor-survival-extrapolation-review
description: Prepare and audit AI4HEOR survival fitting and extrapolation reviews from an already-generated local fit bundle. Use when comparing a pre-specified set of standard parametric curves, separating observed and extrapolated time, recording statistical and graphical diagnostics, testing clinical and external plausibility, documenting structural alternatives, or preparing a curve recommendation for Human selection. This alpha imports exact survHE execution evidence but does not fit patient-level data; never auto-select a curve or claim scientific approval.
---

# HEOR Survival Extrapolation Review

Create one auditable comparison per absolute survival curve, not an automatic model selector. Use `heor/survival-extrapolation-review.json` for one plan target or the fixed collection manifest `heor/survival-extrapolation-reviews.json` for 2–32 targets. Read `references/survival-extrapolation-contract.md` before preparing either form.

## Workflow

1. Read the decision problem, conceptual model, evidence synthesis, analysis plan, input provenance, and data classification. Confirm each endpoint, population, curve label, time origin, event and censor definition, time unit, observed follow-up boundary, and modeled horizon in natural language. Preserve the plan's exact parametric-survival target order. Copy the current `analysis_id` and each exact `input_provenance[].path` into its review's `analysis_target`.
2. Stop if the data classification or local execution boundary is unresolved. This alpha accepts only an already-generated local fit bundle and its manifest; do not open, transform, fit, or transmit patient-level input.
3. Pre-specify 2–8 candidate families before fitting. Use only the bounded first-slice families in the contract. Record why each candidate is included; do not add or remove a family after seeing results without declaring a protocol deviation.
4. Import execution evidence from a Human-controlled local R environment with pinned `survHE` and dependencies. Do not run the fit in this alpha, install packages silently, or bundle GPL code into the deterministic core. Capture the fit-bundle SHA-256, exact command or script SHA-256, R version, package versions, session information, and every generated fit/plot file hash.
5. Fit one absolute curve per review artifact. Multiple reviews may cover control/intervention or PFS/OS plan targets independently, but the collection does not establish cross-curve consistency. Keep treatment-effect synthesis, proportional-hazards pooling, treatment switching, PFS/OS combination rules, competing risks, cure or mixture models, reconstructed IPD, and flexible splines outside this contract.
6. Compare every pre-specified model. Record convergence, AIC, BIC, log likelihood, parameterization, common survival and hazard landmarks, Kaplan–Meier overlay, log-cumulative-hazard view, hazard view, and any protocol deviation. Failed fits remain visible.
7. Separate the observed period from extrapolation. Include at least one common landmark inside observed follow-up and one beyond it. Check survival monotonicity, non-negative hazards, expected hazard shape, external evidence, biological and clinical plausibility, and a representative structural scenario set.
8. Write an analyst recommendation only when its model is converged and all competing candidates remain visible. State why statistical fit alone is insufficient and identify at least one alternative. Set the gate state only to `awaiting_human_selection`.
9. For one target, run `scripts/validate_survival_extrapolation_review.py heor/survival-extrapolation-review.json --workspace <project-root> --analysis-plan heor/analysis-plan.json`. For 2–32 targets, write one schema `0.2.0` review under `heor/survival-extrapolation-reviews/` per target, then create the ordered schema `0.1.0` manifest and run `scripts/validate_survival_extrapolation_collection.py heor/survival-extrapolation-reviews.json --workspace <project-root> --analysis-plan heor/analysis-plan.json`. Fix every structural, target-order, hash, landmark, or completeness error. The desktop analysis-plan approval independently repeats the audit and binds the manifest plus every referenced review.
10. After Human selection, route only a supported already-selected exponential or Weibull absolute curve to `$heor-survival-curve-adapter`. Keep other families and all unresolved clinical validity questions explicit until a separately admitted calculation contract exists.

## Boundaries

- Do not auto-rank or auto-select by AIC, BIC, visual fit, or a composite score.
- Do not hide failed models, post-hoc family changes, implausible tails, or uncertainty outside the trial period.
- Do not convert a recommendation, review basis, plot, package output, or agent statement into approval.
- Do not claim that a checklist establishes internal validity, external validity, proportional hazards, independent validation, reimbursement suitability, or policy advice.
- Do not execute an external fitting package in this alpha. A future isolated backend requires a separately admitted patient-level data and app-owned execution contract.
- Do not infer PFS ≤ OS, treatment-arm alignment, curve non-crossing, joint covariance, or partitioned-survival validity from a complete collection; those require separate deterministic contracts.

## Resources

- `references/survival-extrapolation-contract.md`: exact artifact, method, execution, and stopping rules.
- `assets/survival-extrapolation-review.template.json`: copyable draft artifact.
- `assets/survival-extrapolation-reviews.template.json`: ordered multi-target collection manifest.
- `scripts/validate_survival_extrapolation_review.py`: standalone structural, landmark, hash, and Human-gate validator.
- `scripts/validate_survival_extrapolation_collection.py`: standalone plan-order, per-review, and collection-hash validator.
