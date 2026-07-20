# RWE causal-analysis contract

## Scientific boundary

Schema `0.2.0` implements one Human-prespecified active-comparator new-user target-trial analysis with a fixed-horizon binary outcome that may be unobserved because of loss to follow-up. Each eligible person contributes one baseline row and one explicit outcome-observation indicator. The estimand is the source-cohort average treatment-effect risk difference if every person's outcome were observed at the fixed horizon.

The Human defines the target trial, estimand, every baseline treatment-outcome common cause, the subset also used as observation-outcome predictors, and the scientific acceptability of all diagnostics. The engine never selects variables, changes the design, or determines causal validity.

The engine fits two unpenalized main-effects logistic models: treatment conditional on all declared baseline confounders, and outcome observation conditional on treatment plus the declared observation predictors. Continuous predictors use deterministic sample mean/standard-deviation scaling. There are no interactions, nonlinear terms, model search, regularization, fallback estimators, or outcome regression.

For each row, the stabilized treatment weight is the marginal probability of the observed treatment divided by its fitted conditional probability. For an observed outcome, the stabilized observation weight is the treatment-arm observation probability divided by its fitted conditional observation probability; an unobserved outcome receives zero analysis weight. Their product estimates arm-specific fixed-horizon risks and the risk difference. Weights are not trimmed, capped, or renormalized.

## Identification assumptions and exclusions

Interpretation as the requested causal effect requires consistency, treatment exchangeability conditional on the declared baseline confounders, observation exchangeability conditional on treatment and the declared baseline observation predictors, joint positivity, and correct specification of both models. These assumptions are not established by model convergence, covariate balance, overlap, or plausible-looking weights.

This contract handles only a single fixed-horizon observation indicator. It does not handle time-varying censoring, intermittent observation, treatment switching, non-adherence strategies, survival or time-to-event outcomes, competing risks, repeated outcomes, clustering, missing baseline covariates, imputation, missing-not-at-random mechanisms, time-varying confounding, matching, trimming, overlap weighting, outcome regression, AIPW/TMLE, g-methods beyond this baseline weighting contract, negative controls, or quantitative bias analysis.

## Data, diagnostics, and deterministic uncertainty

The CSV columns are exactly `subject_id,treatment,outcome_observed,outcome` followed by request-ordered numeric baseline covariates. Outcome is `0` or `1` when observed and blank when not observed. All other cells must be present and finite. Subjects are unique safe pseudonyms. Each treatment arm has at least 20 people, at least two observed and two unobserved outcomes, and among observed outcomes at least two events and two non-events. The contract allows at most 5,000 rows and 12 baseline variables.

Outputs contain no row-level data. They report both model fits, treatment propensity overlap, arm follow-up rates, treatment/observation/combined weight distributions, treatment-only and observed-row combined effective sample sizes, pre-weight, treatment-weight, and combined-observed-weight balance, observed complete-case contrasts, the primary combined-weight contrast, and explicit limitations. No diagnostic threshold produces automatic acceptance.

Uncertainty uses a fixed PCG32 arm-stratified whole-row bootstrap. Every replicate refits standardization and both logistic models, reconstructs all weights, and recalculates the risk difference. Every failure is retained and blocks review; there is no retry or replacement. The portable audit repeats the complete bootstrap and hash graph. The desktop native audit independently repeats source parsing, both point models, weights, effects, balance, overlap, and ESS.

## Human gate

The desktop owns an immutable eight-check Human method review. Acceptance only makes the exact result eligible for later evidence selection. It does not approve the target trial, prove a causal effect, establish regulatory-grade evidence, select treatment, or automatically populate an economic model.

## Evidence basis

- NICE recommends target-trial emulation, aligned time zero, explicit censoring definitions, assessment of missingness across groups and over time, methods such as inverse probability weighting when the observation mechanism can be adequately modeled, and sensitivity or bias analysis when it cannot. <https://www.nice.org.uk/corporate/ecd9/chapter/methods-for-real-world-studies-of-comparative-effects>
- NICE's reporting appendix requires explicit discussion of informative censoring, its treatment in the analysis, missing-data mechanisms, and residual risks. <https://www.nice.org.uk/corporate/ecd9/chapter/appendix-2-reporting-on-methods-used-to-minimise-risk-of-bias>
- Hernán and Robins show that inverse probability weights for treatment and censoring can be multiplied to estimate a fixed-horizon effect if nobody were censored, under exchangeability, joint positivity, and consistency. <https://miguelhernan.org/whatifbook>
- Cole and Hernán describe constructing stabilized treatment and censoring weights, diagnosing positivity and model specification, and the assumptions needed to address measured confounding and selection bias. <https://pmc.ncbi.nlm.nih.gov/articles/PMC2732954/>
- Austin and Stuart describe treatment-weight diagnostics, effective sample size, and weighted covariate balance. <https://pubmed.ncbi.nlm.nih.gov/26238958/>
- Jackson describes balance diagnostics across censoring levels as a validity check for inverse-probability-of-censoring weights. <https://pubmed.ncbi.nlm.nih.gov/31145432/>

These sources support the method and review boundary. They do not validate any dataset, predictor set, model, causal claim, or downstream decision.
