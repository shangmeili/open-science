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

The package binds the exact current bytes of:

- `heor/report.md`
- `heor/analysis-plan.json`
- `heor/conceptual-model.json`
- `heor/uncertainty-plan.json`
- `heor/budget-impact-plan.json`
- `heor/model-validation.json`
- `heor/results/base-case.json`
- `heor/results/uncertainty.json`
- `heor/results/budget-impact.json`

The desktop writes result files after deterministic execution. The release gate
re-executes all three calculations and compares exact output hashes, so a
workspace-authored substitute cannot become authoritative merely by matching a
schema.

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

`result_summary` copies the defined scalars from the three deterministic result
files. Values must match exactly, including `null` when the ICER is undefined.
The report must distinguish cost effectiveness, uncertainty, and affordability.
A favorable value in one analysis cannot be presented as proof of another or as
a reimbursement recommendation.

## Disclosure and authority

Funding, conflicts of interest, Agent contributions, model providers,
data/model availability, and patient/public involvement are required explicit
statements. Empty or inferred disclosures are invalid.

`release_owner_label` is copied only from an explicit human instruction and
must exactly match the actor in the app-owned release approval. Release also
requires a current independent-validation approval and current bindings for all
upstream approvals. Identity remains a local human assertion until an
OS-backed signature and external anchor are implemented.

## Primary sources

- Husereau et al., CHEERS 2022 statement and explanation/elaboration.
- Sullivan et al., ISPOR Budget Impact Analysis Good Practice II, 2014.
- Chinese Pharmaceutical Association, China Guidelines for Pharmacoeconomic
  Evaluations 2020, T/CPHARMA 003-2020.
