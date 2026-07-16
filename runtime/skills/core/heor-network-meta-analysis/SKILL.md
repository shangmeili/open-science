---
name: heor-network-meta-analysis
description: Prepare, execute, audit, and explain one bounded local frequentist network meta-analysis using contrast-level two-arm randomized-study effects and an isolated user-installed netmeta R library. Use when a researcher needs a connected three-to-32-treatment evidence network, common-effect or REML random-effects estimates, heterogeneity, prediction intervals, direct-versus-indirect diagnostics, optional P-scores, or an app-owned Human model review before reusing an NMA estimate in HEOR. Reject multi-arm studies, arm-level likelihoods, disconnected networks, automatic model or treatment selection, Bayesian NMA, meta-regression, population adjustment, and unreviewed downstream use.
---

# HEOR Network Meta-Analysis

Prepare one outcome-specific contrast-based NMA under researcher-defined choices. Read [references/network-meta-analysis-contract.md](references/network-meta-analysis-contract.md) before drafting or executing the request.

## Workflow

1. Confirm the population, intervention nodes, comparator definitions, outcome, timepoint, estimand, eligible randomized parallel studies, and why all treatments are jointly randomizable. Use a separate request for every outcome and timepoint.
2. Confirm a current hash-bound `heor/evidence-synthesis.json` and a local UTF-8 CSV with exactly `study_id,treat1,treat2,effect,se`. Require one unique two-arm study per row, 3–32 declared treatments, positive finite standard errors, a connected network, no direct identifiers, and complete study-to-evidence provenance.
3. Stop for multi-arm, cluster, crossover, observational, disconnected, dose-response, component, individual-patient, arm-level, or mixed-design networks. Do not split multi-arm studies into independent rows.
4. Ask the researcher to select one admitted effect scale (`log_odds_ratio`, `log_risk_ratio`, `log_hazard_ratio`, `mean_difference`, or `standardized_mean_difference`), one reference treatment, favorable direction, and either a common-effect model or a common-heterogeneity REML random-effects model. Never select a model from fit statistics or p-values.
5. Record effect-modifier distributions for every direct comparison, node definitions and merging rationales, risk of bias, transitivity concerns, planned design-decomposition and node-splitting diagnostics, optional descriptive P-scores, and limitations. A non-significant inconsistency test never establishes transitivity.
6. Probe the Human-supplied isolated R library without installing or updating packages:

   `python3 scripts/run_netmeta.py probe --rscript <Rscript> --library <isolated-library>`

7. Copy [assets/network-meta-analysis-request.template.json](assets/network-meta-analysis-request.template.json) to `heor/network-meta-analysis-request.json`, fill the exact R/package/adapter identity returned by the probe, and run:

   `python3 scripts/validate_nma_request.py heor/network-meta-analysis-request.json --workspace <project-root>`

8. Present the exact fixed run command for Human command authorization. Only after authorization, run:

   `python3 scripts/run_netmeta.py run heor/network-meta-analysis-request.json --workspace <project-root> --rscript <Rscript> --library <isolated-library>`

9. Validate the resulting manifest with `scripts/validate_nma_execution.py <manifest> --workspace <project-root>`. The portable auditor independently rebuilds the contrast design and weighted least-squares network. For random effects it reproduces estimates conditional on the backend-reported tau; it does not independently estimate REML tau.
10. Ask the researcher to use the native review pane for the exact request/result hashes and all eight model-review checks. Only an accepted app-owned review may make the result eligible for downstream evidence selection. Never create the review record or copy an estimate into an economic model automatically.

## Interpretation boundary

- Lead with network geometry, effect scale, model, tau and prediction intervals, heterogeneity, global/local inconsistency, transitivity concerns, risk of bias, and uncertainty—not ranking.
- Label P-scores as descriptive summaries of relative-effect estimates and uncertainty. Do not call the top score the best treatment or a reimbursement recommendation.
- Distinguish statistical consistency from clinical transitivity and substantive validity.
- Keep GPL R packages outside the MIT deterministic core. Bundle only the first-party adapter, normalized outputs, validators, hashes, and review contract.
- Treat network-enabled environment variables as defense in depth; the external R process is not an operating-system sandbox.

## Resources

- `references/network-meta-analysis-contract.md`: method, artifact, review, and stopping rules.
- `assets/network-meta-analysis-request.template.json`: copyable request.
- `scripts/nma_contract.py`: dependency-free request/result contract and independent WLS evaluator.
- `scripts/validate_nma_request.py`: request preflight.
- `scripts/run_netmeta.py`: isolated probe and execution orchestrator.
- `scripts/netmeta_adapter.R`: fixed no-install R adapter.
- `scripts/validate_nma_execution.py`: portable result audit.
