# AI4HEOR survival curve materialization contract 0.2.0

## Admitted evaluators

The evaluator identity is exactly `ai4heor-parametric-survival` version `0.2.0`. Time is in years. It admits the natural parameterizations exported by flexsurv through the first-party survHE adapter:

- `exponential_rate`: `rate_per_year`.
- `weibull_shape_scale_aft`: `shape`, `scale_years`.
- `gompertz_shape_rate`: `shape_per_year`, `rate_per_year`.
- `gamma_shape_rate`: `shape`, `rate_per_year`.
- `generalized_gamma_prentice`: `mu_log_years`, `sigma`, `Q`.
- `generalized_f_prentice`: `mu_log_years`, `sigma`, `Q`, `P`.
- `lognormal_meanlog_sdlog`: `meanlog_years`, `sdlog`.
- `loglogistic_shape_scale`: `shape`, `scale_years`.

Rates, scales, ordinary shapes, `sigma`, and `sdlog` are positive; `P` is non-negative; Gompertz shape, `mu`, meanlog, and `Q` may be signed. The Weibull form is AFT shape/scale, not PH rate/shape. A negative Gompertz shape can imply non-zero limiting survival and therefore requires explicit clinical review even when numerically reproduced.

## Required bindings

The manifest binds the exact analysis bytes and is itself bound by the partitioned-survival plan. It contains every strategy's PFS then OS curve in declared strategy order. Each curve binds:

- the exact first-party schema `0.3.0` review and Human-selected converged family;
- one normalized execution model JSON whose path and hash equal that selected review model;
- exact family, parameterization, and parameter values mapped without unit inference from that fit output;
- the fixed evaluator identity and every cycle-boundary value.

Each curve basis list is exactly:

1. `review-sha256:<review digest>`
2. `fit-output-sha256:<fit digest>`
3. `evaluator:ai4heor-parametric-survival@0.2.0`

Every corresponding PSM source value carries that same ordered list unless a later admitted treatment-effect-duration artifact deterministically derives the final rows. Any byte, order, target, family, parameter, time, value, or basis drift fails closed.

## Method basis

NICE DSU TSD 14 recommends a systematic survival-extrapolation process and assessment of alternative models. The flexsurv distribution reference defines the admitted natural parameterizations. These sources support explicit evaluation after selection; they do not authorize automatic selection or validate a specific extrapolation.

- <https://sheffield.ac.uk/nice-dsu/tsds/survival-analysis>
- <https://chjackson.github.io/flexsurv/articles/distributions.pdf>
- <https://chjackson.github.io/flexsurv/reference/flexsurvreg.html>
- <https://chjackson.github.io/flexsurv/reference/GenGamma.html>
- <https://chjackson.github.io/flexsurv/reference/GenF.html>

## Compatibility and exclusions

Schema `0.1.0` with evaluator `0.1.0` remains a compatibility path for exact schema `0.2.0` external reviews and strict exponential/Weibull typed fit outputs. It does not admit the additional families.

Stop for fitting, automatic selection, coefficient transformation without a reviewed export, covariates, treatment-effect application, covariance or PSA, model averaging, splines, cure or mixture models, competing risks, reconstructed IPD, or substantive internal/external validity claims. Those require separately admitted contracts.
