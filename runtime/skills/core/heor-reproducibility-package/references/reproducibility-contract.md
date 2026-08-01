# AI4HEOR reproducibility-package contract

`heor/reproducibility-package.json` is the bounded release companion for the current `heor/report-package.json`. It cannot approve or release itself.

## Scope

Schema `0.1.0` covers the deterministic Markov and partitioned-survival release graph. Schema `0.2.0` covers the deterministic decision-tree graph. Each records what an independent party would need to locate the evidence, inspect the exact model artifacts, and invoke the same first-party calculations. Neither bundles source data, creates a repository archive, installs software, executes external code, or proves that a result is scientifically reproducible.

The researcher directs package preparation in natural language and decides what can be shared. The Skill assists by deriving the structured companion from already reviewed artifacts. Structured fields exist so the portable validator and native desktop can fail closed before the existing Human release gate.

## Artifact inventory

Bind `heor/report-package.json`, every exact path/hash in its `bindings`, and `heor/evidence-synthesis.json` when the analysis plan contains that exact binding. The inventory is an exact set, not an open-ended attachment list. Roles are `release_manifest`, `report`, `method`, `input`, `result`, and `evidence`.

For Markov/PSM, the report package already binds the complete current non-PSM or linked-PSM release graph. Large joint-survival draws and lower-level survival execution artifacts remain transitively bound by the audited uncertainty, materialization, and review artifacts; schema `0.1.0` does not duplicate them in the top-level inventory.

For a decision tree, bind the exact schema `0.3.0` report package plus its six report bindings: decision-tree plan, base result, uncertainty plan, uncertainty result, evidence synthesis, and report document. Do not add Markov, PSM, or budget-impact artifacts to this inventory.

## Deterministic replay recipes

For Markov/PSM record exactly three executions in this order:

1. `cost_effectiveness`: run the current analysis or PSM and write the bound base result.
2. `uncertainty`: run the current uncertainty plan, adding the exact PSM inputs and joint-survival manifest/draw arguments when required.
3. `budget_impact`: run the current analysis and budget-impact plan.

Commands are token arrays rooted at `python -m heor_core heor/analysis-plan.json`. Input and output artifact IDs must match the inventory. Engine versions are copied from the corresponding app-written results. All three use `byte_replay_expected`; the desktop still performs the authoritative replay at release.

For a decision tree record exactly two executions in this order: the base calculation rooted at `python -m heor_core heor/decision-tree-plan.json`, then uncertainty using the same command plus `--decision-tree-uncertainty-plan heor/decision-tree-uncertainty-plan.json`. Bind only the matching decision-tree inputs and results. Do not invent a budget-impact execution.

## Environment boundary

Record current AI4HEOR, OS/architecture, and Python versions. Record the exact set of result engine versions. The bundled HEOR core uses only the Python standard library, so `core_dependency_lock` is `not_applicable_standard_library_only` with zero packages and no fake lock path or hash.

This boundary does not cover external survival fitting, bootstrap refitting, Stata, R, or arbitrary user Python dependencies. Their already bound execution/session artifacts remain review evidence and any portability limitation must remain visible.

## Source and data availability

For Markov/PSM, `source_register` must equal the unique union of `evidence_sources` in the analysis and budget-impact plans. For a decision tree, collect the exact `source_id` values used by the decision-tree plan, resolve each to an extraction in the bound evidence synthesis, and then resolve that extraction to its exact bibliographic record. Copy source metadata; do not infer missing titles, dates, locators, hashes, licenses, or access rights.

`data_availability` must cover every source ID exactly once. Allowed availability states are:

- `included_workspace`
- `public_locator`
- `available_on_request`
- `restricted_not_shared`
- `unavailable`

Allowed license states are `open`, `permission_required`, `restricted`, `unknown`, and `not_applicable`. Every entry requires explicit access conditions and rationale. A public URL is only a locator. A local hash proves current bytes, not truth or redistribution permission.

## Exhibits and claims

For Markov/PSM register exactly three exhibits: `cost_effectiveness`, `uncertainty`, and `budget_impact`. For a decision tree register exactly two exhibits: `cost_effectiveness` and `uncertainty`. Each must link the corresponding deterministic result and at least one claim.

The Markov/PSM ledger contains exactly seven entries and covers each of these reporting items once:

- `CHEERS-2022:23-summary-results`
- `CHEERS-2022:24-uncertainty-effects`
- `CHEERS-2022:26-findings-limitations-generalisability`
- `ISPOR-BIA-GP-II-2014:bia-8-period-disaggregated-results`
- `ISPOR-BIA-GP-II-2014:bia-9-cumulative-impact`
- `ISPOR-BIA-GP-II-2014:bia-10-uncertainty-scenarios`
- `ISPOR-BIA-GP-II-2014:bia-12-limitations-reproducibility`

The decision-tree ledger contains exactly three entries and covers only the CHEERS 2022 items 23, 24, and 26 above. It must not claim budget-impact coverage.

Every claim has a unique ID, statement, type, status, artifact IDs, and an explicit source-ID array, which may be empty only when neither plan declares a supporting source. `supported` and `qualified` mean only that declared links are structurally present. A qualified claim requires a qualification. `not_verifiable` cannot satisfy a required release claim.

## Release boundary

The native audit repeats path, hash, recipe, environment, source, availability, exhibit, and claim checks. Release remains the existing Human-owned gate. Its approval event targets the report package and additionally binds this exact reproducibility package plus the report graph. The desktop replays the analysis-specific calculations before appending the event.

A structurally complete decision-tree report draft produces only a structurally complete reproducibility draft. It does not become release-ready while the report remains draft, proposed assumptions remain unresolved, the evidence synthesis is not ready, the reference case is not current, or uncertainty convergence has not passed.

Changing the report, any bound artifact, the reproducibility package, the current runtime identity, or a required link makes release incomplete or stale. This is local SHA-256 and local actor-label assurance, not authenticated identity, signing, timestamping, or third-party replication.
