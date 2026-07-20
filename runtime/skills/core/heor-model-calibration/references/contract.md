# Bounded cohort natural-history calibration contract 0.1.0

## Admitted question

The researcher supplies one homogeneous continuous-time cohort state-transition model with 2–6 states, an initial distribution, fixed directed rates, and 1–4 unknown directed rates. Targets are aggregate state-occupancy proportions at integer cycles for the same population and time origin. The engine returns candidate point estimates; it does not alter an economic model.

The model generator is converted to each cycle transition matrix by uniformization with tail tolerance `1e-14` and at most 512 terms. The maximum total exit rate at the declared upper bounds multiplied by cycle length cannot exceed 30.

## Targets and objective

Each target declares provenance, population alignment, observed occupancy, and standard error. The standard error only scales its residual. Target covariance is not modeled, so the sum of squared standardized calibration residuals is not described as a likelihood, chi-square sampling claim, or posterior density.

Targets are assigned before execution to `calibration` or held-out `validation`. At least one validation target and more calibration targets than parameters are mandatory. Held-out targets never contribute to the search objective.

## Fixed deterministic search

The engine evaluates a seven-level tensor grid over each linear or log-scaled bounded parameter, keeps the best eight objective-then-lexicographic starts, and applies coordinate pattern search. The step halves when no neighbor improves, stops below normalized step `1e-7`, and permits at most 500 iterations per start. Every evaluation is written to `search.csv`; all local solutions are reported.

## Diagnostics, not automatic decisions

At the selected point, finite differences of scaled calibration-target predictions form a local Jacobian. Eigenvalues of its cross-product provide numerical rank and a condition index over the identifiable subspace. This is only a local numerical diagnostic: it neither proves global identifiability nor authorizes silently selecting among equivalently fitting parameter sets.

Held-out RMSE and maximum absolute residual are descriptive. There is no automatic threshold for fit, identifiability, validation, or acceptance.

## Excluded from schema 0.1.0

- treatment effects, costs, utilities, ICERs, reimbursement conclusions, or model optimization;
- target covariance, formal likelihood claims, Bayesian/posterior calibration, or probabilistic calibration;
- calibrated-parameter uncertainty propagation or target resampling;
- individual/microsimulation, time-varying rates, covariates, competing structural models, or structural calibration;
- automatic target, parameter, bound, model, or fit-threshold selection;
- direct or automatic replacement of downstream model inputs.

These limits reflect established calibration reporting concerns: parameters and targets must be explicit, goodness of fit and search/stopping rules must be reported, convergence must be checked, and nonidentifiability can change decisions even when fits appear similar. Primary methodological sources include Vanni et al. (2011), Stout et al. (2009), Briggs et al. (2012), Alarid-Escudero et al. (2018), and the ISPOR-SMDM validation task force.
