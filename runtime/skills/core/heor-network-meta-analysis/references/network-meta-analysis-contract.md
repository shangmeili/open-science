# Network meta-analysis contract

Schema `0.1.0` implements one contrast-based frequentist NMA for one outcome and timepoint. It is an evidence-synthesis analysis, not an economic result or decision rule.

## Admitted statistical model

- Input rows are independent two-arm randomized-study contrasts with observed effect `treat1 - treat2` and its standard error.
- The network contains 3–32 treatments and must be connected. Repeated direct comparisons are allowed; every `study_id` occurs once.
- The sampling model is normal with identity link on the declared effect scale. Log OR, log RR, and log HR are exponentiated only for presentation; computation remains on the log scale.
- The researcher selects either a common-effect consistency model or a random-effects consistency model with one common heterogeneity variance and REML tau estimation.
- The backend is a fixed adapter over a Human-supplied isolated `netmeta` R library. No installation, package update, network request, arbitrary R code, or serialized model object is admitted.
- The portable and native evaluators rebuild the treatment design and weighted least-squares solution. Random-effects reproduction is conditional on backend tau; REML tau estimation remains a separately disclosed backend dependency.

## Required scientific review

The request must bind node definitions, evidence-synthesis bytes, every contributing record, study-level provenance and risk of bias, joint-randomizability rationale, and effect-modifier summaries for every direct comparison. The native Human review covers:

1. question, outcome, timepoint, estimand, effect direction and effect scale;
2. node definitions, merging decisions, network connectivity and the two-arm boundary;
3. eligible studies, extracted contrasts, standard errors, provenance and risk of bias;
4. joint randomizability, effect-modifier balance and transitivity concerns;
5. common versus random model, common tau assumption and REML dependency;
6. heterogeneity, tau and prediction intervals where applicable;
7. global design-decomposition and local direct-versus-indirect diagnostics, including non-estimability in a tree network;
8. ranking limitations, uncertainty, downstream transportability and unresolved limitations.

Acceptance records a local Human assertion over exact request/result hashes. It is not authenticated identity, independent statistical validation, GRADE/CINeMA certainty, clinical validity, or permission to release a reimbursement claim.

## Stop boundary

Reject multi-arm trials rather than treating correlated contrasts as independent. Also reject arm-level binomial/Poisson/normal likelihoods, zero-cell correction, disconnected networks, cluster or crossover designs, observational evidence, dose-response or component NMA, network meta-regression, subgroup NMA, class effects, IPD, population adjustment, Bayesian priors/MCMC, automated node merging, automated model choice, automatic treatment selection, and automatic economic-model population. Use a separately admitted method when any excluded feature is material.

## Evidence basis

The contract follows the separation in Cochrane Handbook chapter 11 between clinical transitivity, within-comparison heterogeneity, and statistical incoherence; the NICE DSU TSD 2–4 model/heterogeneity/inconsistency sequence; and NICE Appendix K / PRISMA-NMA reporting expectations. `netmeta` is an execution backend, not methodological authority.
