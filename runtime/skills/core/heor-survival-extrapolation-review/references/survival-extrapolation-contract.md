# Survival extrapolation review contract

## Scope

Create one review per absolute time-to-first-event curve. The review layer accepts either an eligible `$heor-survival-fit-execution` bundle or an independently generated local fit bundle; it does not itself read or fit individual time-to-event data. It compares standard parametric maximum-likelihood model outputs without selecting one automatically.

Schema `0.2.0` preserves the external local-fit import contract. Schema `0.3.0` binds an AI4HEOR isolated local MLE result manifest and must exactly reproduce its target, candidate order, runtime, normalized model outputs, diagnostics, and hashes after the portable and native execution audits pass. Every ready artifact binds exact local evidence by lowercase SHA-256.

`analysis_target` must contain the current analysis plan's exact `analysis_id` and one exact `input_provenance[].path` whose transformation operation is `parametric_survival_to_transition_schedule`. The Human-selected plan distribution must be a converged, pre-specified candidate in that review.

For one target, the fixed path is `heor/survival-extrapolation-review.json`. For 2–32 targets, use the schema `0.1.0` manifest at `heor/survival-extrapolation-reviews.json`; each referenced review must be one safely named JSON file directly under `heor/survival-extrapolation-reviews/`. Manifest entries contain only `target_path`, `review_path`, and `review_sha256`, and must exactly match the plan's survival-target count and order. Target paths and review paths are unique. The app-owned approval boundary re-hashes and re-audits every review, then binds the manifest and all referenced review files to the analysis-plan approval. Missing, extra, duplicated, reordered, stale, malformed, or out-of-workspace entries fail closed.

The collection is an integrity and completeness envelope for independently reviewed curves. It does not yet check PFS ≤ OS, arm or time-origin alignment, curve crossings, correlated parameters, joint structural scenarios, or partitioned-survival validity.

## Candidate set

Pre-specify 2–8 unique families from:

- `exponential`
- `weibull`
- `gompertz`
- `gamma`
- `generalized_gamma`
- `generalized_f`
- `lognormal`
- `loglogistic`

Every candidate declares a non-empty rationale. The artifact's model results must contain exactly the same families in the same order. A post-fit change requires a non-empty `protocol_deviations` record; it does not silently rewrite the pre-specification.

This schema does not admit splines, cure or mixture models, relative survival, competing risks, recurrent events, multi-state fitting, treatment switching, reconstructed IPD, covariate adjustment, pooled proportional-hazards effects, or Bayesian fitting.

## Common landmarks

All converged models use the same strictly increasing landmark times. Include time zero with survival 1, at least one positive time no later than `observed_follow_up`, and at least one time later than `observed_follow_up` but no later than `model_horizon`. Survival is finite, in `[0,1]`, and non-increasing. Hazard is finite and non-negative. These checks catch malformed exports; they do not prove clinical plausibility.

## Required evidence views

A ready review binds:

- Kaplan–Meier overlay with all converged candidates;
- log-cumulative-hazard diagnostic;
- hazard diagnostic over observed and extrapolated time;
- external-validity assessment with at least one cited source or an explicit unresolved statement;
- clinical/biological plausibility assessment of long-term survival and hazard shape;
- at least two structural scenarios, including the recommended curve when a recommendation is present.

AIC and BIC compare relative in-sample fit only. Do not turn them into a pass threshold or scientific-validity score.

## survHE execution evidence

The fit bundle originates from a Human-controlled, user-installed isolated R environment. Schema `0.2.0` imports the following evidence. Schema `0.3.0` accepts only the corresponding normalized fields from an eligible first-party result manifest and independently re-audits that manifest:

- `R.version.string`;
- `survHE`, `flexsurv`, and `survival` versions;
- complete `sessionInfo()` output;
- exact local command or script path and SHA-256;
- exact fit-bundle manifest path and SHA-256;
- generated model object, fit table, predictions, and plot hashes.

`survHE::fit.models` can fit multiple named distributions and reports model-fit statistics, but package output is not approval. Keep GPL packages outside the MIT deterministic core and do not auto-install them. The first-party execution slice is limited to authorized, strict two-column local CSV input, intercept-only MLE, and an already-installed isolated library. A missing, ineligible, stale, or mismatched execution manifest means the review remains draft.

## Human gate

The only admitted gate object is:

```json
{
  "state": "awaiting_human_selection",
  "required_action": "select_curve_in_analysis_plan"
}
```

The review may contain an analyst recommendation, but no `approved`, `selected`, `accepted`, reviewer identity, signature, or approval timestamp field. The Human selects each downstream curve by reviewing the complete analysis plan; the app-owned analysis-plan approval chain independently re-audits every schema `0.2.0` or `0.3.0` review, matches each exact analysis target and selected distribution, verifies local hashes and any first-party execution bundle, and binds either the single review or the complete collection.

## Method basis

NICE PMG36 requires extrapolation assumptions to have internal and external validity, alternative scenarios, assessment of proportional hazards where relevant, clinical plausibility of hazard functions, and explicit uncertainty in extrapolated hazards. NICE DSU TSD14 requires systematic comparison rather than statistical or visual fit alone and emphasizes external data, biological plausibility, and clinical expert opinion. The official `survHE` documentation describes its multiple-distribution fitting and AIC/BIC outputs.

Primary sources:

- [NICE PMG36 economic evaluation](https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2/)
- [NICE DSU TSD14 survival analysis](https://www.sheffield.ac.uk/sites/default/files/2022-02/TSD14-Survival-analysis.updated-March-2013.v2.pdf)
- [survHE fit.models documentation](https://search.r-project.org/CRAN/refmans/survHE/help/fit.models.html)

## Downstream boundary

After Human selection, `$heor-survival-curve-adapter` can evaluate only an exact already-selected exponential or Weibull parameterization in a two-state absorbing schedule. A review collection does not make other fitted families executable in the deterministic economic model and does not establish PFS/OS consistency or partitioned-survival validity.
