---
name: heor-rwe-causal-analysis
description: Prepare, execute, audit, and explain one bounded local real-world evidence target-trial analysis with a Human-prespecified active-comparator new-user cohort, fixed-horizon binary outcome that may be unobserved, baseline treatment-outcome confounders and observation-outcome predictors, stabilized treatment and observation weights, deterministic refitted bootstrap uncertainty, and app-owned Human method review. Use when a researcher needs an auditable source-cohort risk difference if nobody's fixed-horizon outcome were lost from local pseudonymous data already reduced to one eligible baseline row per person. Reject automatic design or variable selection, causal-validity claims, missing baseline covariates, time-varying censoring or confounding, survival outcomes, competing risks, trimming, matching, doubly robust estimators, missing-not-at-random claims, and unreviewed downstream use.
---

# HEOR RWE Causal Analysis

Keep the researcher in scientific control. Assist with preparation, deterministic local execution, audit, and explanation; never choose the target trial, eligibility criteria, time zero, treatments, outcome, confounders, estimand, diagnostic acceptability, or downstream use.

## Route the method before touching data

1. Use this Skill only for the fixed contract in [references/rwe-causal-analysis-contract.md](references/rwe-causal-analysis-contract.md).
2. Require a Human-defined active-comparator new-user target trial with one baseline row per eligible person, two treatments assigned at time zero, one fixed-horizon binary outcome, an explicit observation indicator, and baseline variables measured before treatment.
3. Stop when eligibility, assignment, time zero, follow-up, or outcome measurement are misaligned; when the active comparator or new-user restriction is absent; or when material confounders are unavailable.
4. Admit only fixed-horizon outcome loss explained by the prespecified measured baseline predictors conditional on treatment. Route time-varying censoring, treatment switching, time-varying treatment/confounding, competing risks, survival outcomes, repeated observations, clustering, missing baseline covariates, imputation, missing-not-at-random mechanisms, matching, overlap weighting, g-computation, doubly robust estimation, instrumental variables, difference-in-differences, self-controlled designs, negative controls, or quantitative bias analysis to separately admitted methods. Do not approximate them here.

## Prepare the request through conversation

1. Start from `assets/rwe-causal-analysis-request.template.json`. Write `heor/rwe-causal-analysis-request.json` only after the researcher defines all seven target-trial dimensions, the source-population ATE risk-difference estimand if nobody's outcome were lost, the treatment encoding, every baseline treatment-outcome common cause, every observation-model predictor, and limitations.
2. Require one strict pseudonymous CSV with `subject_id,treatment,outcome_observed,outcome` followed by the declared numeric baseline columns. Permit a blank outcome only when `outcome_observed=0`; reject direct identifiers, any other missing/non-finite value, repeated subjects, post-treatment variables, or treatments other than the two declared strategies.
3. Bind the exact local evidence-synthesis artifact and every confounder's evidence records. Never infer that a measured variable is a confounder merely because it predicts treatment or outcome.
4. Classify patient-level data before execution. Keep rows and row-derived artifacts local; never send them to a model or connector.
5. Explain that both treatment and observation exchangeability, joint positivity, consistency, and correct model specification are required. Diagnostics do not prove these assumptions, missing-at-random behavior, correct measurement, transportability, or absence of residual bias.

## Validate, authorize, and execute

Run from the Skill directory:

```bash
python3 scripts/validate_rwe_causal_request.py \
  --workspace /absolute/workspace \
  --request heor/rwe-causal-analysis-request.json
```

After the researcher authorizes the exact local command, run:

```bash
python3 scripts/run_rwe_causal_analysis.py \
  --workspace /absolute/workspace \
  --request heor/rwe-causal-analysis-request.json
```

The runner installs nothing, uses only the Python standard library, writes atomically, and emits no row-level data. It refits both prespecified logistic models and reconstructs treatment, observation, and combined weights in every fixed PCG32 arm-stratified bootstrap replicate. Every failed replicate is retained and blocks review eligibility.

Audit the result independently through the portable replay:

```bash
python3 scripts/audit_rwe_causal_result.py \
  --workspace /absolute/workspace \
  --result heor/rwe-causal-analysis-runs/<execution_id>/manifest.json
```

## Hand off to Human review

Leave a complete result at `awaiting_method_review`. The desktop, not this Skill, owns acceptance or rejection and requires all eight checks:

- target trial, estimand, eligibility, assignment, time zero, follow-up, and outcome;
- data provenance, active-comparator/new-user construction, and cohort eligibility;
- confounder causal rationale, timing, completeness, and measurement;
- observation indicator and outcome-cell integrity, follow-up patterns and causes, and privacy;
- treatment and observation model specification, joint positivity, overlap, and separate/combined weight distributions;
- pre/treatment/combined balance, observed-row effective sample size, convergence, and influential observations;
- bootstrap failures, precision, and sensitivity-analysis omissions;
- residual bias, consistency, transportability, limitations, and downstream suitability.

Acceptance only makes the exact result eligible for later evidence selection. It does not prove a causal effect, approve an analysis plan, select a treatment, establish regulatory-grade evidence, or automatically populate an economic model.
