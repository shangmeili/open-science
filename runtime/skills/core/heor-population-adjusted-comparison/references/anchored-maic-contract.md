# Anchored MAIC contract

## Scientific boundary

Schema `0.1.0` implements one connected, two-trial anchored comparison across two independent randomized parallel-arm trials. Trial `AB` supplies IPD for treatment `B` and common comparator `A`. Trial `AC` supplies aggregate relative-effect evidence for treatment `C` versus `A` and target-population means for every declared effect modifier. The estimand is the marginal `B` versus `C` effect in the `AC` trial population on either the log-odds-ratio or mean-difference scale.

The Human prespecifies every effect modifier on the chosen scale. The engine centers each IPD covariate at its `AC` target mean and solves the exponential-tilting method-of-moments equations. It uses positive, untrimmed, mean-one weights and requires numerical convergence and exact declared-mean balance. Prognostic-only variables are not admitted in the anchored weighting set because randomization and the common-comparator contrast protect against their imbalance within each trial; including unnecessary variables can reduce overlap and precision.

The weighted `B:A` effect is subtracted from the independent aggregate `C:A` effect on the same linear-predictor scale. Binary outcomes use marginal weighted arm risks and a log odds ratio. Continuous outcomes use a weighted mean difference. The result also reports the unadjusted IPD contrast so the effect of population adjustment is visible; neither estimate is interpreted automatically.

## Data and privacy

The IPD CSV columns are exactly `subject_id,treatment,outcome` followed by the request-ordered effect-modifier columns. Subjects are unique safe pseudonyms. There are exactly two declared randomized arms, at least 20 rows per arm, no missing or non-finite values, and at most 5,000 rows and eight effect modifiers. Binary outcomes are exactly `0` or `1`; continuous outcomes are finite and bounded in absolute value. The aggregate JSON has an exact schema and binds the target trial, target population, treatments, effect scale, target means, evidence record IDs, and aggregate estimate/standard error.

IPD remains local. Outputs contain aggregate diagnostics, coefficients, effects, and bootstrap draws only; they do not copy subject identifiers, covariates, treatments, or outcomes. Unsafe paths, symlinks, stale hashes, direct identifiers, unknown classification, or remote execution fail closed.

## Deterministic execution and audit

The fixed evaluator is `ai4heor-anchored-maic@0.1.0`. Calibration uses damped Newton iteration with a deterministic pivoted linear solver and no penalty, clipping, trimming, or fallback optimizer. A singular Hessian, overflow, nonconvergence, or residual imbalance fails explicitly.

Uncertainty uses the shared `pcg32-xsh-rr` version `1` stream. Every replicate resamples complete rows with replacement separately within the two randomized arms, refits calibration weights, and recalculates the weighted `B:A` contrast. The final `B:C` standard error is the square root of the bootstrap variance of `B:A` plus the squared independent aggregate `C:A` standard error. Every failure is written to the draw file and makes the result incomplete and not reviewable; there is no silent retry, replacement, or complete-case filtering.

The runner binds the exact request, IPD, aggregate evidence, evidence synthesis, evaluator source, Python executable, and draw bytes. The portable audit repeats the complete request validation, calibration, point estimate, PCG32 resampling, every bootstrap refit, variance composition, interval, weight diagnostics, and hash graph. Native Rust independently repeats request/source/hash checks, calibration, balance, ESS, weight diagnostics, unadjusted and adjusted point estimates, and indirect-comparison arithmetic. Native Rust does not replay every bootstrap optimization and must not be described as an independent uncertainty implementation.

## Human gate and exclusions

The desktop writes an immutable review snapshot plus a separate private unanchored SHA-256 event chain. All eight method checks are required for acceptance. A later rejection for the same execution invalidates earlier acceptance. Agents can prepare or explain the record but cannot write either authority.

Reject unanchored MAIC, single-arm or observational evidence, disconnected comparisons, more than two trials or treatments per trial, aggregate-only adjustment, STC, ML-NMR, outcome regression, survival/time-to-event effects, risk ratios, hazard ratios, SMD, subgroup interactions, higher moments, categorical encodings, missing-data imputation, covariate selection, prognostic-only matching, weight trimming/capping, alternative calibration estimators, cluster/crossover designs, treatment switching, nonindependent aggregate evidence, automatic interpretation, and automatic economic-model use.

## Evidence basis

The method boundary follows NICE DSU TSD 18 and the corresponding NICE technology-appraisal manual: use connected randomized evidence when available, preserve the common comparator, justify scale-specific effect modifiers before analysis, work on the usual linear-predictor scale, expose target population and overlap, report weight distributions and effective sample size, and acknowledge residual systematic error. Later simulation evidence shows that missing effect modifiers can bias every population-adjustment method and that MAIC can perform poorly even when it exactly balances declared moments. This implementation therefore treats successful calibration as a diagnostic fact, never proof of unbiasedness.
