# Isolated survHE execution contract

## Scope

Request and normalized-model schema `0.1.0` fit one absolute right-censored time-to-event curve using intercept-only maximum likelihood. Current result schema `0.2.0` adds hash-bound source-model parameter-uncertainty artifacts; legacy result `0.1.0` remains readable. The source is one strict UTF-8 CSV with exactly two columns: positive finite time and binary event. Use one independently authorized request per endpoint, arm, population, and time origin.

The admitted candidate set is exponential, Weibull, Gompertz, gamma, generalized gamma, generalized F, lognormal, and loglogistic. Every request pre-specifies 2–8 unique candidates and includes exponential and Weibull. The fixed R adapter invokes `survHE::fit.models` once per family so one failed fit cannot erase the other attempts. It exports only aggregate fit statistics, natural-scale parameter estimates from `flexsurvreg$res`, estimation-scale coefficients and covariance from `flexsurvreg$res.t` and `flexsurvreg$cov`, requested survival/hazard landmarks, warnings, session information, and diagnostic images. It never serializes a fitted model object because `survHE` and `flexsurv` objects may retain patient-level data.

## Request

The request binds:

- safe execution ID and exact analysis target;
- local-only classification, relative CSV path, SHA-256, column names, exact row/event/censor counts, and explicit absence of direct identifiers;
- intercept-only MLE, ordered candidate set and rationales;
- 3–256 common prediction times starting at zero, covering observed and extrapolated periods, and ending at the model horizon;
- observed follow-up equal to the maximum source time;
- independent-check tolerance from `1e-12` through `1e-6`;
- exact expected `survHE`, `flexsurv`, and `survival` versions;
- fixed new output directory and fail-if-present policy;
- limitations and an `awaiting_execution_authorization` Human gate.

The preflight rejects symlinks, paths outside the workspace, stale hashes, extra or reordered columns, non-binary events, non-positive/non-finite time, missing events, unknown classification, authority fields, and post-hoc candidate changes. It does not assess whether the dataset, censoring mechanism, candidate set, or horizon is scientifically appropriate.

## Isolation and execution

`run_survhe_mle.py` receives `Rscript` and an existing isolated library as explicit command arguments. It never installs or updates a package. It invokes `Rscript --vanilla` with an argument array, excludes user and site profiles, limits `.libPaths()` to the declared library plus base R, refuses package-version drift, redirects stdin, captures bounded output, and fails if the output directory exists. Proxy variables point to a closed loopback port as defense in depth. This is not an OS network sandbox; the fixed adapter's absence of installation and network operations is part of the auditable code boundary.

The output binds the exact request and current source bytes, R executable hash, R version, exact package versions, copied adapter hash, session information, execution log, one normalized JSON file per attempted model, one covariance-status binding per attempted model, and three diagnostics. Failed fits remain visible. No `.RDS` or copied patient-level data enters the bundle.

## Source-model parameter uncertainty

For each converged family, result schema `0.2.0` writes one `parameter-uncertainty/<family>.json` artifact. An available artifact binds the normalized model bytes and records the exact estimation-scale parameter order, coefficient vector, full covariance matrix, explicit `identity` or `exp` inverse transform per parameter, inverse-observed-Hessian method, and asymptotic multivariate-normal sampling basis. The portable Python and native Rust auditors independently require finite values, exact family-specific order and transforms, symmetry within `1e-10`, positive definiteness by Cholesky decomposition, and recovery of every bound natural-scale parameter within numerical tolerance.

When `flexsurv` does not expose a finite full-dimension symmetric positive-definite covariance matrix, the artifact remains hash-bound with status `unavailable` and the backend reason. AI4HEOR does not repair, shrink, jitter, project, or reconstruct it. Covariance availability is reported separately from point-fit eligibility so a scientifically reviewable fit is not silently discarded.

This covariance describes dependence among parameters of one intercept-only absolute curve. It does not contain within-person PFS/OS dependence or between-strategy dependence. The result therefore declares `scope=within_model_curve_only` and `joint_curve_draw_authority=false`; independently sampling several such artifacts cannot satisfy `$heor-joint-survival-uncertainty`.

## Independent numerical challenge

Evaluator `ai4heor-survival-crosscheck@0.2.0` independently recomputes survival and positive-time hazard for exponential, Weibull AFT, Gompertz, gamma, generalized gamma, generalized F, lognormal, and loglogistic models from their exported natural parameters. The interchange represents hazard at time zero as `null` for every family because the limit may be zero, finite, or infinite.

Every converged model's requested survival and positive-time hazard values must agree with the `flexsurv` predictions exported through the survHE fit within the pre-specified absolute tolerance. Failed fits remain `fit_failed`; no converged admitted family can bypass the check as `not_applicable`. Agreement detects interface and parameterization drift; it does not validate the statistical model or evidence.

## Human and downstream boundary

An eligible execution requires current hashes, exact versions, at least two converged candidates, successful exponential and Weibull baseline fits, and a passed independent check for every converged candidate. It then routes to `$heor-survival-extrapolation-review`; it never selects a curve. Human review remains responsible for data fitness, censoring assumptions, proportional-hazards questions, statistical and graphical fit, external evidence, clinical plausibility, extrapolation, alternatives, and downstream structure.

Covariates, arms in one model, left truncation, interval censoring, competing or recurrent events, relative survival, treatment switching, reconstructed IPD, cure/mixture/spline models, Bayesian inference, joint PFS/OS modeling, cross-curve covariance, joint draw generation, and probabilistic model averaging remain outside result schema `0.2.0`.

## Upstream basis

CRAN stable `survHE` `2.0.51` was published on 15 January 2026 under GPL-3-or-later and requires R 4.1 or newer. Its documented `fit.models` interface supports MLE through `flexsurv` and Bayesian modules separately. The development repository reported `2.0.52` when this contract was written. AI4HEOR records exact installed versions rather than silently treating either as a method default.

Primary sources:

- [CRAN survHE package page](https://cran.r-project.org/package=survHE)
- [survHE fit.models documentation](https://search.r-project.org/CRAN/refmans/survHE/help/fit.models.html)
- [survHE source repository](https://github.com/giabaio/survHE)
- [flexsurvreg model-object and covariance documentation](https://chjackson.github.io/flexsurv/reference/flexsurvreg.html)
- [flexsurv normal-theory simulation documentation](https://chjackson.github.io/flexsurv/reference/normboot.flexsurvreg.html)
- [NICE PMG36 economic evaluation](https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2/)
- [NICE DSU TSD14 survival analysis](https://www.sheffield.ac.uk/sites/default/files/2022-02/TSD14-Survival-analysis.updated-March-2013.v2.pdf)
