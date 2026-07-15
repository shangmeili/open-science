---
name: heor-survival-fit-execution
description: Execute and audit a pre-specified intercept-only maximum-likelihood survival fit in a user-installed isolated survHE R library. Use when AI4HEOR must fit one local absolute time-to-event curve, preserve every attempted standard parametric model, generate fixed diagnostic evidence, or independently cross-check exponential and Weibull predictions before survival extrapolation review. Never install packages, select a curve, or treat numerical agreement as scientific validity.
---

# HEOR Survival Fit Execution

Run one bounded local fitting job whose request, source CSV, R executable, fixed adapter, package versions, outputs, and diagnostics are auditable. Read [references/execution-contract.md](references/execution-contract.md) before creating or running a request.

## Workflow

1. Confirm the exact absolute survival target, endpoint, population, time origin, event and censor definitions, observed follow-up, model horizon, and pre-specified candidate families in natural language. Use a separate request for every curve. Do not combine PFS, OS, treatment arms, or populations in one run.
2. Confirm that the local CSV contains exactly two columns: one positive finite time and one binary `0`/`1` event indicator. Reject missing values, direct identifiers, extra columns, symlinks, unresolved classification, or any need for data egress. This first slice does not admit covariates, left truncation, interval censoring, competing/recurrent events, reconstructed IPD, cure/mixture/spline models, treatment switching, or Bayesian fitting.
3. Probe the Human-supplied isolated library without installing or updating anything:

   `python3 scripts/run_survhe_mle.py probe --rscript <Rscript> --library <isolated-library>`

   Record the exact reported `survHE`, `flexsurv`, and `survival` versions in the request. Stop when the packages are absent or differ from the request; never run `install.packages` from this Skill.
4. Copy [assets/survival-fit-execution-request.template.json](assets/survival-fit-execution-request.template.json) to a safely named file under `heor/survival-fit-requests/`. Populate exact row/event/censor counts, current SHA-256, candidate rationales, a common observed/extrapolated prediction grid ending at the model horizon, exact package versions, limitations, and the fixed output directory. Include both exponential and Weibull so the independent evaluator can challenge the backend.
5. Run `python3 scripts/validate_survhe_fit_request.py <request> --workspace <project-root>`. Fix every path, hash, data-shape, pre-specification, version, horizon, or authority error before execution.
6. Present the exact fixed command for Human authorization. Only after the app's command-approval gate permits it, run:

   `python3 scripts/run_survhe_mle.py run <request> --workspace <project-root> --rscript <Rscript> --library <isolated-library>`

   The runner uses an argument array rather than a shell, disables user/site R profiles, refuses version drift and existing output, captures failures, and never installs a package. It copies the fixed adapter into the result bundle and hashes all generated evidence.
7. Run `python3 scripts/validate_survhe_fit_execution.py <result-manifest> --workspace <project-root>`. The portable validator re-reads the request and current CSV, verifies every file hash, and independently recalculates exponential and Weibull survival and hazard values from exported parameters. Stop if it reports incomplete or ineligible.
8. Route an eligible bundle to `$heor-survival-extrapolation-review`. Preserve all attempted models and backend warnings, assess observed and extrapolated periods, external evidence, hazard shape, clinical plausibility, and structural alternatives. Leave the curve gate `awaiting_human_selection`; only a later Human-reviewed analysis plan may select a curve.

## Boundaries

- Do not install R, `survHE`, or dependencies; do not modify a shared R library.
- Do not infer or write patient-level values, formulae, candidate families, package versions, or approval state.
- Do not run if the source contains direct identifiers or more than the two admitted columns.
- Do not auto-rank or select by AIC, BIC, plots, convergence, or cross-implementation agreement.
- Do not claim OS/PFS consistency, treatment-arm alignment, parameter covariance, internal validity, external validity, clinical plausibility, independent validation, or release readiness.
- Treat the network-blocking environment variables as defense in depth, not an operating-system network sandbox. The fixed adapter contains no network or installation operation, but the user-installed R process remains an external tool.
- Keep GPL packages outside the MIT deterministic core and bundle only the first-party adapter, request, normalized outputs, diagnostics, and hashes.

## Resources

- `references/execution-contract.md`: exact scope, artifact, isolation, cross-check, license, and stopping rules.
- `assets/survival-fit-execution-request.template.json`: copyable request draft.
- `scripts/validate_survhe_fit_request.py`: dependency-free preflight.
- `scripts/run_survhe_mle.py`: fixed Python orchestrator and runtime probe.
- `scripts/survhe_mle_adapter.R`: fixed R adapter with no package installation or network calls.
- `scripts/validate_survhe_fit_execution.py`: dependency-free result and cross-implementation audit.
