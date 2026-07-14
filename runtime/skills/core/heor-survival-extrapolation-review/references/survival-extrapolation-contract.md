# Survival extrapolation review contract

## Scope

Create one review per absolute time-to-first-event curve. The first slice accepts an already-generated local fit bundle and execution manifest; it does not read or fit individual time-to-event data. It compares standard parametric maximum-likelihood model outputs without selecting one automatically.

The artifact path is `heor/survival-extrapolation-review.json`; schema version is `0.2.0`. Every ready artifact binds the exact local input, execution record, session information, model outputs, and diagnostic files by lowercase SHA-256.

`analysis_target` must contain the current analysis plan's exact `analysis_id` and the exact `input_provenance[].path` whose transformation operation is `parametric_survival_to_transition_schedule`. The Human-selected plan distribution must be a converged, pre-specified candidate in this review. The app-owned approval boundary requires exactly one such mapping in this alpha and fails closed for multi-curve plans; a future indexed collection contract is required before multiple curve reviews can be approved together.

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

## Imported survHE execution evidence

The fit bundle may originate from a Human-controlled, user-installed isolated R environment. This alpha imports the following evidence but does not execute the fit or copy approval state into this agent-authored artifact:

- `R.version.string`;
- `survHE`, `flexsurv`, and `survival` versions;
- complete `sessionInfo()` output;
- exact local command or script path and SHA-256;
- exact fit-bundle manifest path and SHA-256;
- generated model object, fit table, predictions, and plot hashes.

`survHE::fit.models` can fit multiple named distributions and reports model-fit statistics, but package output is not approval. Keep GPL packages outside the MIT deterministic core and do not auto-install them. Patient-level fitting and a first-party isolated R backend remain unshipped. A missing execution manifest or unverified fit bundle means the review remains draft; it must not be described as a completed fit.

## Human gate

The only admitted gate object is:

```json
{
  "state": "awaiting_human_selection",
  "required_action": "select_curve_in_analysis_plan"
}
```

The review may contain an analyst recommendation, but no `approved`, `selected`, `accepted`, reviewer identity, signature, or approval timestamp field. The Human selects the downstream curve by reviewing the complete analysis plan; the app-owned analysis-plan approval chain independently re-audits schema `0.2.0`, matches the exact analysis target and selected distribution, verifies local hashes, and binds the current review SHA-256.

## Method basis

NICE PMG36 requires extrapolation assumptions to have internal and external validity, alternative scenarios, assessment of proportional hazards where relevant, clinical plausibility of hazard functions, and explicit uncertainty in extrapolated hazards. NICE DSU TSD14 requires systematic comparison rather than statistical or visual fit alone and emphasizes external data, biological plausibility, and clinical expert opinion. The official `survHE` documentation describes its multiple-distribution fitting and AIC/BIC outputs.

Primary sources:

- [NICE PMG36 economic evaluation](https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2/)
- [NICE DSU TSD14 survival analysis](https://www.sheffield.ac.uk/sites/default/files/2022-02/TSD14-Survival-analysis.updated-March-2013.v2.pdf)
- [survHE fit.models documentation](https://search.r-project.org/CRAN/refmans/survHE/help/fit.models.html)

## Downstream boundary

After Human selection, `$heor-survival-curve-adapter` can evaluate only its exact already-selected exponential or Weibull parameterization in a two-state absorbing schedule. This review does not make other fitted families executable in the deterministic economic model and does not establish PFS/OS consistency or partitioned-survival validity.
