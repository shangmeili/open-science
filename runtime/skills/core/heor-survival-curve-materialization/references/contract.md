# AI4HEOR survival curve materialization contract 0.1.0

## Admitted evaluators

The evaluator identity is exactly `ai4heor-parametric-survival` version `0.1.0`. Time is in years.

- Exponential rate: `S(t) = exp(-rate_per_year * t)`.
- Weibull accelerated-failure-time shape/scale: `S(t) = exp(-(t / scale_years) ^ shape)`.

All parameters are finite and strictly positive. The Weibull parameterization is the AFT shape/scale form used by `dweibull` and `flexsurvreg(dist="weibull")`; it is not Weibull PH rate/shape and not the coefficients printed by `survreg` before transformation.

## Required bindings

The manifest binds the exact analysis bytes and is itself bound by partitioned-survival schema `0.2.0`. It contains every strategy's PFS then OS curve in declared strategy order. Each curve binds:

- the exact schema `0.2.0` review and Human-selected converged family;
- one strict typed fit-output JSON whose path and hash equal that selected review model;
- exact family, parameterization, and positive parameter values from that fit output;
- the fixed evaluator identity and every cycle-boundary value.

Each curve basis list is exactly:

1. `review-sha256:<review digest>`
2. `fit-output-sha256:<fit digest>`
3. `evaluator:ai4heor-parametric-survival@0.1.0`

Every corresponding PSM value carries that same ordered list. Any byte, order, target, family, parameter, time, value, or basis drift fails closed.

## Method basis

NICE DSU TSD 14 recommends a systematic survival-extrapolation process and assessment of alternative models. The flexsurv distribution reference defines exponential rate and distinguishes Weibull AFT shape/scale from Weibull PH rate/shape. These sources support explicit evaluation after selection; they do not authorize automatic selection or validate a specific extrapolation.

- <https://sheffield.ac.uk/nice-dsu/tsds/survival-analysis>
- <https://chjackson.github.io/flexsurv/articles/distributions.pdf>
- <https://chjackson.github.io/flexsurv/reference/flexsurvreg.html>

## Exclusions

Stop for fitting, automatic selection, coefficient transformation without a reviewed export, covariates, treatment-effect application, covariance or PSA, model averaging, splines, cure or mixture models, generalized families, competing risks, reconstructed IPD, or substantive internal/external validity claims. Those require separately admitted contracts.
