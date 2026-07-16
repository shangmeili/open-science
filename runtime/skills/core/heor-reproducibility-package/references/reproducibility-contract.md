# AI4HEOR reproducibility-package contract

`heor/reproducibility-package.json` is the bounded release companion for the current `heor/report-package.json`. It cannot approve or release itself.

## Scope

Schema `0.1.0` covers the currently supported deterministic AI4HEOR release graph. It records what an independent party would need to locate the evidence, inspect the exact model artifacts, and invoke the same first-party calculations. It does not bundle source data, create a repository archive, install software, execute external code, or prove that a result is scientifically reproducible.

The researcher directs package preparation in natural language and decides what can be shared. The Skill assists by deriving the structured companion from already reviewed artifacts. Structured fields exist so the portable validator and native desktop can fail closed before the existing Human release gate.

## Artifact inventory

Bind `heor/report-package.json`, every exact path/hash in its `bindings`, and `heor/evidence-synthesis.json` when the analysis plan contains that exact binding. The inventory is an exact set, not an open-ended attachment list. Roles are `release_manifest`, `report`, `method`, `input`, `result`, and `evidence`.

The report package already binds the complete current non-PSM or linked-PSM release graph. Large joint-survival draws and lower-level survival execution artifacts remain transitively bound by the audited uncertainty, materialization, and review artifacts; schema `0.1.0` does not duplicate them in the top-level inventory.

## Deterministic replay recipes

Record exactly three executions in this order:

1. `cost_effectiveness`: run the current analysis or PSM and write the bound base result.
2. `uncertainty`: run the current uncertainty plan, adding the exact PSM inputs and joint-survival manifest/draw arguments when required.
3. `budget_impact`: run the current analysis and budget-impact plan.

Commands are token arrays rooted at `python -m heor_core heor/analysis-plan.json`. Input and output artifact IDs must match the inventory. Engine versions are copied from the corresponding app-written results. All three use `byte_replay_expected`; the desktop still performs the authoritative replay at release.

## Environment boundary

Record current AI4HEOR, OS/architecture, and Python versions. Record the exact set of result engine versions. The bundled HEOR core uses only the Python standard library, so `core_dependency_lock` is `not_applicable_standard_library_only` with zero packages and no fake lock path or hash.

This boundary does not cover external survival fitting, bootstrap refitting, Stata, R, or arbitrary user Python dependencies. Their already bound execution/session artifacts remain review evidence and any portability limitation must remain visible.

## Source and data availability

`source_register` must equal the unique union of `evidence_sources` in the analysis and budget-impact plans. Copy source metadata; do not infer missing titles, dates, locators, hashes, licenses, or access rights.

`data_availability` must cover every source ID exactly once. Allowed availability states are:

- `included_workspace`
- `public_locator`
- `available_on_request`
- `restricted_not_shared`
- `unavailable`

Allowed license states are `open`, `permission_required`, `restricted`, `unknown`, and `not_applicable`. Every entry requires explicit access conditions and rationale. A public URL is only a locator. A local hash proves current bytes, not truth or redistribution permission.

## Exhibits and claims

Register exactly three exhibits: `cost_effectiveness`, `uncertainty`, and `budget_impact`. Each must link the corresponding deterministic result and at least one claim.

The ledger contains exactly seven entries and covers each of these reporting items once:

- `CHEERS-2022:23-summary-results`
- `CHEERS-2022:24-uncertainty-effects`
- `CHEERS-2022:26-findings-limitations-generalisability`
- `ISPOR-BIA-GP-II-2014:bia-8-period-disaggregated-results`
- `ISPOR-BIA-GP-II-2014:bia-9-cumulative-impact`
- `ISPOR-BIA-GP-II-2014:bia-10-uncertainty-scenarios`
- `ISPOR-BIA-GP-II-2014:bia-12-limitations-reproducibility`

Every claim has a unique ID, statement, type, status, artifact IDs, and an explicit source-ID array, which may be empty only when neither plan declares a supporting source. `supported` and `qualified` mean only that declared links are structurally present. A qualified claim requires a qualification. `not_verifiable` cannot satisfy a required release claim.

## Release boundary

The native audit repeats path, hash, recipe, environment, source, availability, exhibit, and claim checks. Release remains the existing Human-owned gate. Its approval event targets the report package and additionally binds this exact reproducibility package plus the report graph. The desktop replays all three calculations before appending the event.

Changing the report, any bound artifact, the reproducibility package, the current runtime identity, or a required link makes release incomplete or stale. This is local SHA-256 and local actor-label assurance, not authenticated identity, signing, timestamping, or third-party replication.
