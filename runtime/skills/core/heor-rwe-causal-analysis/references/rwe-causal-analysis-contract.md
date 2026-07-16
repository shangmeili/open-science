# RWE causal-analysis contract

## Scientific boundary

Schema `0.1.0` implements one comparative-effect analysis that emulates a Human-prespecified target trial from an observational active-comparator new-user cohort. Every eligible person contributes exactly one baseline row, receives one of two treatment strategies at the shared time zero, has fixed complete follow-up, and has one binary outcome observed by the fixed horizon. The estimand is the marginal average treatment effect in the analyzed source cohort on the risk-difference scale.

The Human prespecifies the population, eligibility criteria, treatment strategies, assignment procedure, time zero, follow-up, outcome, causal contrast, and every baseline confounder from causal and domain knowledge. The engine never selects variables from associations, balance, fit statistics, or model performance. It fits one unpenalized main-effects logistic propensity model after deterministic mean/standard-deviation scaling of continuous confounders. Binary confounders remain on their original `0/1` scale. No interactions, nonlinear terms, model search, regularization, outcome regression, or fallback estimator are admitted.

The fixed estimator is stabilized inverse-probability weighting for the source-cohort ATE. The numerator is the observed marginal probability of the person's treatment; the denominator is the fitted propensity for that treatment. Weights are not trimmed, truncated, capped, or renormalized. The engine reports marginal weighted risks and the primary risk difference, with risk ratio and odds ratio as descriptive secondary contrasts when finite. These are computation results under the declared design and assumptions, not automatic causal conclusions.

## Data and privacy

The CSV columns are exactly `subject_id,treatment,outcome` followed by the request-ordered confounder columns. Subjects are unique safe pseudonyms. There are exactly two declared treatment strategies, at least 20 rows and at least two outcome events and non-events per arm, no missing/non-finite values, at most 5,000 rows, and at most 12 confounders. A binary confounder is exactly `0` or `1`; a continuous confounder is finite, bounded in absolute value, and has positive variation. Direct identifiers, dates, free text, post-treatment variables, repeated measurements, and row-level output are prohibited.

The source must already represent the Human-reviewed target-trial cohort construction. This alpha does not query source databases, adjudicate eligibility, derive index dates, resolve treatment episodes, measure follow-up, impute missing values, or detect immortal-time and selection bias automatically. Those upstream transformations remain separately reviewable scientific work.

All patient-level data remains local. Outputs contain only aggregate coefficients, moments, propensity/weight distributions, balance diagnostics, effect estimates, and bootstrap draws. Unsafe paths, symlinks, stale hashes, direct identifiers, unknown classification, or remote execution fail closed.

## Deterministic execution and diagnostics

The fixed evaluator is `ai4heor-rwe-causal@0.1.0`. Logistic regression uses damped Newton iteration with a deterministic pivoted linear solver and no penalty or fallback optimizer. Singularity, quasi/complete separation expressed as nonconvergence, non-finite arithmetic, or fitted propensities at the computational boundary fails explicitly.

For each confounder the engine reports pre-weight and post-weight standardized mean differences. Each SMD uses the corresponding two-arm pooled standard deviation. It also reports treatment-specific propensity summaries, weight summaries, arm-specific and overall effective sample sizes, and empirical cross-arm propensity-range intersection. No diagnostic threshold is converted into automatic scientific acceptance. Finite computation and exact artifact integrity determine review eligibility; adequacy of overlap, balance, and effective sample size remains a Human judgment.

Uncertainty uses a fixed `pcg32-xsh-rr` version `1` stream. Every replicate resamples complete rows with replacement separately within treatment arms, refits standardization and the propensity model, recalculates weights and the risk difference, and records diagnostics. The standard error is the sample standard deviation of successful risk-difference draws, and the interval is the prespecified normal bootstrap interval. Every failure is written to the draw file and makes the result incomplete and not reviewable; there is no silent retry or replacement.

The runner binds the exact request, cohort CSV, evidence synthesis, evaluator source, Python executable, and bootstrap-draw bytes. The portable audit repeats the complete request validation, model fit, weights, diagnostics, PCG32 resampling, every bootstrap refit, uncertainty summary, and hash graph. A desktop native audit may independently replay source/hash validation and the point analysis, but must not claim independent bootstrap validation unless it actually repeats every refit.

## Human gate and exclusions

The desktop writes an immutable review snapshot plus a separate private unanchored SHA-256 event chain. All eight method checks are required for acceptance. A later rejection for the same execution invalidates earlier acceptance. Agents can prepare or explain the record but cannot write either authority.

Reject automatic target-trial design, automatic eligibility/time-zero construction, prevalent-user designs, inactive or inappropriate comparators, more than two strategies, multi-category or continuous treatment, nonbinary outcomes, variable follow-up, censoring, loss to follow-up, treatment switching, time-varying exposure or confounding, survival/time-to-event analysis, competing risks, repeated outcomes, clustering, site effects, missing-data imputation, feature selection, interactions, splines, regularization, trimming/capping, matching, stratification, overlap weights, ATT/ATC estimands, outcome regression, AIPW/TMLE, g-formula, marginal structural models, instrumental variables, regression discontinuity, difference-in-differences, self-controlled designs, negative controls, quantitative bias analysis, automated causal interpretation, and automatic economic-model use.

## Evidence basis

- NICE's Real-World Evidence Framework recommends explicitly specifying target-trial eligibility, treatment strategies, assignment, follow-up, outcomes, causal effect, and analysis; aligning eligibility, assignment, time zero, and follow-up; justifying the estimand and confounding method; assessing overlap, balance, weights, missingness, and sensitivity analyses; and reporting provenance and data fitness. <https://www.nice.org.uk/corporate/ecd9/chapter/methods-for-real-world-studies-of-comparative-effects>
- Hernán and Robins describe target-trial specification and emulation as a structure for causal questions using observational data. <https://pubmed.ncbi.nlm.nih.gov/26994063/>
- Hernán and colleagues show why eligibility, treatment assignment, and follow-up must be aligned at time zero to prevent avoidable immortal-time and selection biases. <https://pubmed.ncbi.nlm.nih.gov/27237061/>
- Lund and colleagues explain the active-comparator new-user design for comparative effectiveness and safety research. <https://pubmed.ncbi.nlm.nih.gov/27891526/>
- Austin describes standardized differences for balance assessment after propensity-score matching or weighting. <https://pubmed.ncbi.nlm.nih.gov/19684288/>
- Austin and Stuart review stabilized IPTW implementation, weight diagnostics, effective sample size, and weighted balance assessment. <https://pubmed.ncbi.nlm.nih.gov/26238958/>
- FDA's final 2023 guidance frames RWD/RWE use around data relevance, reliability, study design, and regulatory traceability; this alpha does not claim regulatory fitness. <https://www.fda.gov/regulatory-information/search-fda-guidance-documents/considerations-use-real-world-data-and-real-world-evidence-support-regulatory-decision-making-drug>
- EMA's Data Quality Framework treats quality as contextual fitness for use and emphasizes transparent data-quality assessment rather than a universal threshold. <https://www.ema.europa.eu/en/about-us/how-we-work/data-regulation-big-data-other-sources/data-quality-framework-medicines-regulation>

These sources support the explicit design, diagnostic, reporting, and review boundary. They do not validate a particular dataset, confounder set, fitted model, causal claim, policy decision, or economic-model input.
