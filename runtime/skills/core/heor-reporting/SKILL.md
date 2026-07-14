---
name: heor-reporting
description: Prepare, audit, and revise a release-reviewable HEOR report package that binds economic-evaluation and budget-impact reports to exact model, validation, and deterministic result artifacts. Use for heor/report-package.json, heor/report.md, CHEERS 2022 reporting, budget-impact reporting, CEAC, CEAF, per-person EVPI, result tables, limitations, funding and conflict disclosures, reproducibility appendices, or preparation of the app-owned release gate without claiming methodological quality or creating release approval.
---

# HEOR Reporting

## Workflow

1. Read `references/report-package-contract.md` before creating or changing a package.
2. Require all three app-owned result files under `heor/results/`. If any is missing, ask the researcher to run the corresponding deterministic analysis in the review panel; never recreate numerical results in prose or code.
3. Copy `assets/report-package.template.json` to `heor/report-package.json` and `assets/report.template.md` to `heor/report.md` when absent.
4. Bind the exact current bytes of the five method artifacts, three deterministic result artifacts, and report document. Preserve the fixed paths and lowercase SHA-256 values.
5. Complete the 28 CHEERS 2022 reporting entries for cost effectiveness. Treat `not_applicable` as an explained reporting state, never as a silent omission or a positive score.
6. Complete the separate 12-item ISPOR BIA reporting matrix. CHEERS 2022 explicitly excludes budget-impact analysis; do not claim CHEERS coverage for BIA.
7. Put a unique `<!-- report-section:SECTION_ID -->` marker in `heor/report.md` for every matrix entry and link each entry to the exact artifact paths supporting it.
8. Copy numerical summaries only from the app-owned result JSON files. When `decision_uncertainty` exists, copy the complete object exactly, including the threshold grid, CEAC/CEAF probabilities, per-person EVPI and Monte Carlo error, and explicit null population EVPI/EVPPI. For a legacy result without the object, retain the legacy summary shape rather than inventing it. Keep cost-effectiveness, uncertainty, and budget-impact conclusions separate.
9. Disclose funding, conflicts, Agent contributions, model providers, data/model availability, and patient/public involvement. Never infer a missing disclosure.
10. Copy `release_owner_label` only from an explicit human instruction. Do not invent an owner, create an approval event, or call a package released.
11. Run `python3 scripts/validate_report_package.py WORKSPACE/heor/report-package.json WORKSPACE`. Treat `valid` as structural reporting readiness, not methodological quality, policy endorsement, or release.
12. Ask the named human release owner to inspect the report and use the desktop release control.

## Boundaries

- Do not score CHEERS or use item counts to claim study quality.
- Do not apply CHEERS to the BIA; use the separate BIA matrix.
- Do not edit files under `heor/results/`; they are written by deterministic app execution.
- Do not hide negative, dominated, uncertain, or unaffordable results.
- Do not turn a cost-effectiveness result into a reimbursement recommendation.
- Do not describe CEAC or CEAF as a policy recommendation. Do not extrapolate per-person EVPI to a population or infer EVPPI, research priority, optimal study design, or funding value.
- Do not omit limitations, unresolved uncertainty, funding, conflicts, or Agent involvement.
- Do not claim identity, independent validation, regulatory acceptance, or release readiness beyond the app's local human-assertion boundary.

## Handoff

Report the package ID and hash, report-document hash, all model/result bindings, matrix gaps, CEAC/CEAF threshold coverage, primary-threshold per-person EVPI and Monte Carlo error, disclosures, limitations, release owner, and exact next human action. State that the app verifies structure, hashes, deterministic result reproduction, reporting coverage, and local approval state—not scientific truth, population value of information, journal acceptance, or policy suitability.
