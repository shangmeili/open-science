---
name: heor-reproducibility-package
description: Prepare and audit the bounded AI4HEOR release companion that binds the current report graph, deterministic replay commands, runtime environment, evidence-source availability, exhibits, and claim-to-evidence ledger. Use for heor/reproducibility-package.json, reproducibility or replication packages, data/model availability statements, command or code inventories, environment locks, source/exhibit registers, claim-evidence traceability, or preparation of a Human-owned release without copying restricted data or creating approval.
---

# HEOR Reproducibility Package

The researcher leads the release preparation and decides what can be shared. This
Skill assists by deriving a bounded companion from researcher-approved artifacts;
it does not direct the study, choose methods or evidence, or own the release.

## Workflow

1. Read `references/reproducibility-contract.md` before creating or changing the package.
2. Require a complete current `heor/report-package.json`. Do not create a reproducibility package around draft, stale, or missing deterministic results.
3. Copy `assets/reproducibility-package.template.json` to `heor/reproducibility-package.json` when absent. Keep it `draft` until every section is complete.
4. Bind the exact current report-package bytes and reproduce its full binding graph in `artifact_inventory`. Add the exact evidence-synthesis binding when the analysis plan declares one. Do not add unrelated workspace files.
5. Record the three fixed AI4HEOR replay recipes: cost effectiveness or PSM, uncertainty, and budget impact. Copy engine versions only from their app-written result artifacts. Never substitute prose, generated code, or a different calculator.
6. Record the current AI4HEOR version, platform, Python version, and dependency boundary. The first-party HEOR core is standard-library-only; do not invent a package lock or claim that an external R/Stata/Python environment is covered by it.
7. Build `source_register` from the exact union of analysis-plan and budget-impact-plan evidence sources. Preserve titles, source types, locators, and local-file hashes without fetching or copying source content.
8. Cover every registered source exactly once through `data_availability`. State whether it is in the workspace, publicly locatable, available on request, restricted and not shared, or unavailable; state license status and access conditions. Do not weaken restricted or unknown classifications.
9. Register exactly the cost-effectiveness, uncertainty, and budget-impact exhibits and link each to its deterministic result artifact and claim IDs.
10. Complete the seven required decision-facing claim entries: CHEERS 2022 items 23, 24, and 26 plus ISPOR BIA items 8, 9, 10, and 12. Link each claim to bound artifacts and registered sources. Qualify limitations explicitly; never convert traceability into a truth or quality claim.
11. Preserve a non-empty limitations list covering unavailable inputs, restricted data, external runtime gaps, structural uncertainty, identity assurance, and any non-reproduced steps that apply.
12. Run `python3 scripts/validate_reproducibility_package.py WORKSPACE/heor/reproducibility-package.json WORKSPACE`. Fix every path, hash, recipe, environment, source, availability, exhibit, and claim error.
13. Ask the named release owner to inspect the package in the desktop review pane. Only the app may replay calculations and bind this package into a release approval event.

## Boundaries

- Do not copy licensed, restricted, patient-level, claims, EHR, or identifiable data into the package.
- Do not claim that a locator makes data available or that a hash establishes source truth.
- Do not describe structural completeness as independent replication, scientific validity, journal compliance, regulatory acceptance, or reimbursement suitability.
- Do not edit app-written result files or approval records.
- Do not create a new approval gate. This package is a required companion bound by the existing Human release gate.

## Handoff

Report the package and report hashes; artifact, execution, environment, source, availability, exhibit, and claim coverage; restricted or unavailable inputs; unresolved reproducibility gaps; and the exact next Human action. State that portable and native audits verify structure, current bytes, replay recipes, and traceability—not source truth, external statistical validity, authenticated identity, or successful reproduction on another machine.
