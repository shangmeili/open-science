# AI4HEOR report-package contract

`heor/report-package.json` is the machine-readable release manifest and
`heor/report.md` is its human-readable report. Neither file can approve or
release itself.

## Method boundary

CHEERS 2022 supplies 28 reporting items for comparative economic evaluations.
It is a reporting guideline, not a methodological-quality instrument or score,
and explicitly places budget-impact analysis outside its scope. AI4HEOR applies
all 28 items only to the cost-effectiveness report.

The separate budget-impact matrix adapts the ISPOR Budget Impact Analysis Good
Practice II reporting format: decision context, population and treatment mix,
costs, sources and derivations, framework, disaggregated period results,
uncertainty, validation, limitations, and reproducibility. When CEA and BIA are
reported together, both sets remain complete and visibly separate.

The China 2020 profile remains the current execution reference case. The China
second-edition consultation draft may inform gap analysis but must remain
labelled draft and cannot replace current requirements or release authority.

## Required files and bindings

Schema `0.1.0` remains the non-PSM contract. Its package binds the exact current bytes of:

- `heor/report.md`
- `heor/analysis-plan.json`
- `heor/conceptual-model.json`
- `heor/uncertainty-plan.json`
- `heor/budget-impact-plan.json`
- `heor/model-validation.json`
- `heor/results/base-case.json`
- `heor/results/uncertainty.json`
- `heor/results/budget-impact.json`

For a linked partitioned-survival analysis, schema `0.2.0` instead requires the exact 15-key set in `assets/psm-report-bindings.template.json`: the report; the five non-report method artifacts above; the PSM plan; the five current materialization, duration, cost, utility, and event inputs; and the PSM, uncertainty, and budget-impact results. The PSM and uncertainty results must reproduce the same source hashes. The exact uncertainty-plan bytes transitively bind any joint-survival manifest and draws; those potentially large files are not duplicated in this bounded report manifest.

For a short-horizon decision tree, report schema `0.3.0` is a separate cost-effectiveness-only contract. It binds exactly `heor/report.md`, `heor/evidence-synthesis.json`, current `heor/decision-tree-plan.json` schema `0.2.0`, `heor/decision-tree-uncertainty-plan.json`, `heor/results/decision-tree.json`, and `heor/results/decision-tree-uncertainty.json`. Every decision-tree `source_id` must identify an extraction in that exact evidence synthesis. It uses CHEERS 2022 only; it does not add an ISPOR BIA matrix or imply that a budget-impact analysis exists. The result and uncertainty result must bind the exact current plan bytes, and the uncertainty result must also bind the exact uncertainty-plan bytes.

A structurally complete decision-tree package may remain `draft` and may be rendered for Human review. It is not release-reviewable while the reference case is not current, the evidence synthesis is not ready for Human review, any plan input still relies on `proposed assumptions`, or the declared PSA convergence check has not passed. Labelling such a package `ready_for_release_review` is an error. Draft status does not authorize the reporting layer to change the plan, replace evidence, relax convergence thresholds, rerun with different inputs, or suppress the reason.

The desktop writes result files after deterministic execution. The release gate
re-executes all three calculations and compares exact output hashes, so a
workspace-authored substitute cannot become authoritative merely by matching a
schema. A structurally complete report must also have a current
`heor/reproducibility-package.json` derived through `$heor-reproducibility-package`.
The existing release event binds that companion; it does not create another gate.

## Reporting matrices

Every required item appears exactly once. Allowed statuses are `reported` and
`not_applicable`. Both require a rationale, one or more supporting bound
artifact paths, and a unique section marker in the report:

```text
<!-- report-section:methods.population -->
```

`not_applicable` records why an item does not apply; it is neither missing nor
passed. The validator reports coverage, not a score.

## Numerical summaries

`result_summary` copies the defined values from the three deterministic result
files. A legacy cost-effectiveness summary copies `economic_basis` exactly
before the pairwise incremental monetary fields. A schema `0.8.0` summary
instead copies the declared strategy order and baseline, condensed totals for
every strategy, all pairwise-vs-baseline results, the complete fully incremental
frontier, and the primary-threshold optimum. Occupancy traces are deliberately
excluded from this report summary but remain bound in the result artifact.
Values must match exactly, including `null` when an ICER or economic basis is
undefined.
For a decision tree, the bounded summary copies the economic basis, strategy order, baseline, strategy cost/QALY/NMB totals, pairwise results, fully incremental frontier, primary-threshold optimum, all DSA rows, and all PSA summary fields except the per-iteration `samples`. Samples remain available and integrity-bound in the uncertainty result; omitting them from the report manifest prevents an unbounded report while preserving exact auditability.
When the uncertainty result contains `decision_uncertainty`, the package copies
that complete object exactly: threshold rows, every strategy's unique-optimal
CEAC probability, separate tie probability, CEAF probabilities,
per-person EVPI and Monte Carlo error, and the explicit null population EVPI
and EVPPI fields. A legacy result without that object keeps the legacy summary
shape; the reporting layer does not manufacture a value-of-information result.
The report must distinguish cost effectiveness, uncertainty, and affordability.
A favorable value in one analysis cannot be presented as proof of another or as
a reimbursement recommendation. Per-person EVPI is conditional on uncertainty
represented in the bound PSA and is not a population research-funding value.

For analysis schema `0.9.0`, the methods and limitations sections report the selected life table's jurisdiction, year, population, sex, start age, and attained-age alignment; the exact conversion `1-exp(-(-ln(1-q_annual)+h_excess)*cycle_length_years)`; the constant excess-rate basis; and the separate `population_exchangeability` and `no_double_counting` bases. These bases are review inputs, not approval claims. The uncertainty section states that schema `0.8.0` varies only the exact excess rate while holding the life table and transformation internals fixed. The limitations section discloses the unsupported multiplicative/SMR alternative and every applicable stopping-rule gap: already all-cause endpoints, mixed cause-specific/subdistribution quantities, calendar improvement, age/sex mixtures, time-varying excess hazards, competing non-death events, and partitioned survival.

For analysis schema `0.10.0`, the methods and limitations sections report the measure, exact interval alignment, baseline-risk schedule, transformation `q*RR` or `q*OR/(1-q+q*OR)`, relative-effect basis, and separate `endpoint_alignment`, `population_transportability`, and `effect_constancy_over_cycles` bases. These are review inputs, not approval claims. The uncertainty section states that schema `0.9.0` varies only `relative_effect.value`, reports the RR ceiling or OR support, and holds baselines and transformation internals fixed. The limitations section discloses every applicable stopping-rule gap, including HR, rate ratio, risk difference, competing events, and treatment-effect extrapolation.

For analysis schema `0.11.0`, the methods and limitations sections report the baseline cumulative-hazard schedule and increments, HR and basis, transformation `-expm1(-HR*(H0(i)-H0(i-1)))`, and separate `endpoint_alignment`, `population_transportability`, `proportional_hazards_assumption`, `effect_constancy_over_horizon`, and `treatment_switching_assessment` bases. These are review inputs, not approval claims. The uncertainty section states that schema `0.10.0` varies only `hazard_ratio.value`, reports the bounded Uniform support and numerical ceiling, and holds baseline hazards and transformation internals fixed. The limitations section discloses every applicable stopping-rule gap, including non-proportional or time-varying effects, waning/stopping, unresolved switching, competing/recurrent events, fitting/selection, and partitioned survival.

## Disclosure and authority

Funding, conflicts of interest, Agent contributions, model providers,
data/model availability, and patient/public involvement are required explicit
statements. Empty or inferred disclosures are invalid.

`release_owner_label` is copied only from an explicit human instruction and
must exactly match the actor in the app-owned release approval. Release also
requires a current independent-validation approval and current bindings for all
upstream approvals, including the exact current reproducibility companion.
Identity remains a local human assertion until an
OS-backed signature and external anchor are implemented.

## Primary sources

- Husereau et al., CHEERS 2022 statement and explanation/elaboration.
- Sullivan et al., ISPOR Budget Impact Analysis Good Practice II, 2014.
- Chinese Pharmaceutical Association, China Guidelines for Pharmacoeconomic
  Evaluations 2020, T/CPHARMA 003-2020.
