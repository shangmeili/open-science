# Advanced VOI contract

## Authority and scope

The Human researcher selects the affected population, technology lifetime,
discounting, parameter groups, study likelihood, candidate designs, costs, and
interpretation. AI4HEOR validates and calculates those choices. It does not
select a research program or create funding, reimbursement, or release authority.

The ISPOR VOI Task Force treats EVPI, EVPPI, EVSI, and ENBS as conditional on the
decision problem and its represented uncertainty. It recommends preserving
parameter dependence, choosing inner/outer simulation sizes for acceptable
bias and precision, matching EVSI's data-generating distribution to the proposed
analysis, and reporting assumptions and research costs explicitly:

- [ISPOR Task Force report 1](https://pubmed.ncbi.nlm.nih.gov/32113617/)
- [ISPOR Task Force report 2, full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC7373630/)

## Supported uncertainty boundaries

- Standard Markov: uncertainty schema `0.9.0`, limited to an odds-ratio target
  with an independent Lognormal distribution for EVSI.
- Current fixed-survival PSM components: uncertainty schema `0.13.0`.
- HR/Uniform schema `0.10.0` cannot satisfy the declared log-scale
  Normal-Normal EVSI contract and is rejected rather than approximated silently.

## Calculations

At the primary threshold `k`, net monetary benefit for strategy `d` and state
of knowledge `theta` is `NMB(d,theta)=k*QALY(d,theta)-Cost(d,theta)`.

Per-person EVPI is copied only from the exact converged uncertainty result:

`E_theta[max_d NMB(d,theta)] - max_d E_theta[NMB(d,theta)]`.

For declared annual affected populations `N_t` and population discount rate
`r`, the effective population is:

`sum_t N_t/(1+r)^t`.

Population EVPI is per-person EVPI times that effective population. Annual
population values are explicit inputs; the engine does not infer incidence,
prevalence, diffusion, displacement, or implementation.

For one correlation-closed group `phi`, nested EVPPI uses outer draws of `phi`
and inner draws of every complementary parameter:

`E_phi[max_d E[NMB(d,theta)|phi]] - max_d E[NMB(d,theta)]`.

The implementation reports a draw-level Monte Carlo standard error. Nested
simulation bias is not removed. Increase inner and outer iterations only after
reviewing precision and runtime; the bounded engine permits at most 100,000
model evaluations for each EVPPI or EVSI section.

EVSI schema `0.1.0` supports one independent Lognormal model parameter. On its
log scale, the current PSA prior is `Normal(mu,sigma^2)`. A proposed study
observes a sample mean with known per-participant standard deviation `s`, so for
sample size `n` the likelihood is `Normal(theta,s^2/n)`. The engine applies the
conjugate Normal posterior, samples posterior parameter values in an inner loop,
and calculates:

`EVSI(n)=E_X[max_d E[NMB(d,theta)|X]]-max_d E[NMB(d,theta)]`.

Only populations affected after the declared study delay enter population EVSI.
For fixed study cost `C_fixed` and per-participant cost `C_unit`:

`ENBS(n)=population_EVSI(n)-C_fixed-n*C_unit`.

## Fail-closed exclusions

- Joint PFS/OS uncertainty, correlated EVSI targets, more than one learned
  parameter, non-Normal likelihoods, allocation ratios, follow-up choices,
  censoring, missingness, measurement error, adaptive designs, and sequential
  research programs are unsupported.
- Structural and omitted parameter uncertainty remain limitations even when
  numerical results pass.
- A finite candidate set is compared exactly as declared. The largest ENBS is
  not described as a globally optimal design.
- Population values are upper bounds only over the affected population and
  uncertainty represented in the bound artifacts.
